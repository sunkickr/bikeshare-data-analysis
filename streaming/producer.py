#!/usr/bin/env python3
"""
GBFS -> Kafka producer for the live CABI station map (Phase 1).

Two modes:
  --dry-run   Fetch the GBFS feeds and print sample records. Uses only the Python
              stdlib, so it works with NO installs and NO Confluent account. Use
              this to verify the GBFS half before wiring Kafka.
  (default)   Produce records to Confluent Cloud topics, keyed by station_id.
              Requires `pip install -r streaming/requirements.txt` and the Kafka
              credentials in .env (see streaming/README.md, Phase 0).

Data plane: producing here IS the Kafka client API. The `confluent` CLI (control
plane) only created the cluster/topics/keys this connects to.

Examples:
  .venv/bin/python streaming/producer.py --dry-run
  .venv/bin/python streaming/producer.py --once          # one poll, then exit
  .venv/bin/python streaming/producer.py                 # poll forever every 60s
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Iterator

# GBFS endpoints (Lyft-hosted; CABI = dca-cabi). Verified 2026-06-14.
STATUS_URL = "https://gbfs.lyft.com/gbfs/2.3/dca-cabi/en/station_status.json"
INFORMATION_URL = "https://gbfs.lyft.com/gbfs/2.3/dca-cabi/en/station_information.json"

# Topic names (created via the confluent CLI in Phase 0).
TOPIC_STATUS = os.environ.get("TOPIC_STATUS", "cabi.station_status")
TOPIC_INFORMATION = os.environ.get("TOPIC_INFORMATION", "cabi.station_information")

POLL_INTERVAL_SECONDS = 60  # GBFS ttl is 60s; polling faster just returns stale data.
USER_AGENT = "bikeshare-data-analysis/live-station-map (learning project)"


# --------------------------------------------------------------------------- #
# Fetch + shape records (stdlib only — testable without Kafka)
# --------------------------------------------------------------------------- #
def fetch_feed(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def status_records(feed: dict) -> Iterator[dict]:
    """One flat record per station, tagged with the feed-level snapshot time."""
    snapshot_ts = feed["last_updated"]
    for st in feed["data"]["stations"]:
        yield {
            "station_id": st["station_id"],
            "snapshot_ts": snapshot_ts,
            "last_reported": st.get("last_reported"),
            "num_bikes_available": st.get("num_bikes_available", 0),
            "num_ebikes_available": st.get("num_ebikes_available", 0),
            "num_bikes_disabled": st.get("num_bikes_disabled", 0),
            "num_docks_available": st.get("num_docks_available", 0),
            "num_docks_disabled": st.get("num_docks_disabled", 0),
            "is_installed": st.get("is_installed", 0),
            "is_renting": st.get("is_renting", 0),
            "is_returning": st.get("is_returning", 0),
        }


def information_records(feed: dict) -> Iterator[dict]:
    snapshot_ts = feed["last_updated"]
    for st in feed["data"]["stations"]:
        yield {
            "station_id": st["station_id"],
            "snapshot_ts": snapshot_ts,
            "name": st.get("name"),
            "short_name": st.get("short_name"),
            "lat": st.get("lat"),
            "lon": st.get("lon"),
            "capacity": st.get("capacity"),
            "region_id": st.get("region_id"),
        }


FEEDS = {
    "status": (STATUS_URL, TOPIC_STATUS, status_records),
    "information": (INFORMATION_URL, TOPIC_INFORMATION, information_records),
}


# --------------------------------------------------------------------------- #
# Dry run
# --------------------------------------------------------------------------- #
def run_dry(feed_name: str) -> None:
    url, topic, builder = FEEDS[feed_name]
    feed = fetch_feed(url)
    records = list(builder(feed))
    print(f"[{feed_name}] would produce {len(records)} records to topic '{topic}'")
    print(f"[{feed_name}] sample record:")
    print(json.dumps(records[0], indent=2))


# --------------------------------------------------------------------------- #
# Produce to Kafka (data plane). confluent_kafka imported lazily so --dry-run
# needs nothing installed.
# --------------------------------------------------------------------------- #
def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _build_producer():
    from confluent_kafka import Producer  # lazy import

    required = ["BOOTSTRAP_SERVERS", "KAFKA_API_KEY", "KAFKA_API_SECRET"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        sys.exit(
            f"Missing Kafka credentials in .env: {', '.join(missing)}.\n"
            "Complete Phase 0 (see streaming/README.md) or use --dry-run."
        )
    return Producer(
        {
            "bootstrap.servers": os.environ["BOOTSTRAP_SERVERS"],
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": os.environ["KAFKA_API_KEY"],
            "sasl.password": os.environ["KAFKA_API_SECRET"],
            "client.id": "cabi-gbfs-producer",
        }
    )


def produce_once(producer, feed_name: str) -> int:
    url, topic, builder = FEEDS[feed_name]
    feed = fetch_feed(url)
    count = 0
    for record in builder(feed):
        producer.produce(
            topic=topic,
            key=record["station_id"],          # keying enables log compaction later
            value=json.dumps(record).encode("utf-8"),
        )
        count += 1
    producer.flush()
    print(f"[{feed_name}] produced {count} records to '{topic}'")
    return count


def run_produce(feeds: list[str], loop: bool) -> None:
    _load_dotenv()
    producer = _build_producer()
    while True:
        for feed_name in feeds:
            try:
                produce_once(producer, feed_name)
            except Exception as exc:  # one bad poll shouldn't kill the loop
                print(f"[{feed_name}] poll failed: {exc}", file=sys.stderr)
        if not loop:
            break
        time.sleep(POLL_INTERVAL_SECONDS)


# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Fetch + print samples; no Kafka, no installs.")
    parser.add_argument("--once", action="store_true", help="Produce a single poll, then exit.")
    parser.add_argument(
        "--feed", choices=["status", "information", "both"], default="both",
        help="Which feed(s) to handle (default: both).",
    )
    args = parser.parse_args()
    feeds = ["status", "information"] if args.feed == "both" else [args.feed]

    if args.dry_run:
        for feed_name in feeds:
            run_dry(feed_name)
        return

    run_produce(feeds, loop=not args.once)


if __name__ == "__main__":
    main()
