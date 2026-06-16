#!/usr/bin/env python3
"""
Kafka -> local Postgres consumer for the live CABI station map (Phase 2).

Reads both topics in a consumer group, deserializes via Schema Registry (the decode
side of the producer's serializer), and writes to local Postgres:
  - station_status      -> raw.cabi_station_status        (append, month-partitioned)
  - station_information -> raw.cabi_station_information    (upsert latest on station_id)

This is a long-running process. Stop it with Ctrl-C (it flushes + commits offsets
cleanly on the way out). Postgres only changes while this is running.

Postgres credentials come from ~/.dbt/profiles.yml (profile bikeshare / target dev) —
same source the dashboard and dbt use. No new secrets.

Examples:
  .venv/bin/python streaming/consumer.py --drain   # consume backlog, exit when caught up
  .venv/bin/python streaming/consumer.py           # run forever, Ctrl-C to stop
"""
from __future__ import annotations

import argparse
import signal
import sys
from datetime import datetime, timezone, date
from pathlib import Path

import yaml

# Reuse the producer's config so topic names + schemas never drift between the two.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from producer import TOPIC_STATUS, TOPIC_INFORMATION, SCHEMA_DIR, FEEDS, _load_dotenv  # noqa: E402

import os  # noqa: E402

GROUP_ID = "cabi-postgres-sink"
BATCH_SIZE = 500
PROFILES_PATH = Path.home() / ".dbt" / "profiles.yml"

_running = True  # flipped by SIGINT/SIGTERM for a clean shutdown


def _read_pg_profile() -> dict:
    """Pull the bikeshare dev target out of ~/.dbt/profiles.yml (same as dashboard)."""
    with PROFILES_PATH.open() as f:
        profiles = yaml.safe_load(f)
    return profiles["bikeshare"]["outputs"]["dev"]


def _connect_pg():
    import psycopg2

    p = _read_pg_profile()
    return psycopg2.connect(
        host=p["host"], port=p["port"], user=p["user"],
        password=p["password"], dbname=p["dbname"],
    )


def _build_consumer(offset_reset: str):
    from confluent_kafka import Consumer

    for k in ("BOOTSTRAP_SERVERS", "KAFKA_API_KEY", "KAFKA_API_SECRET"):
        if not os.environ.get(k):
            sys.exit(f"Missing {k} in .env. See streaming/README.md.")
    return Consumer({
        "bootstrap.servers": os.environ["BOOTSTRAP_SERVERS"],
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": os.environ["KAFKA_API_KEY"],
        "sasl.password": os.environ["KAFKA_API_SECRET"],
        "group.id": GROUP_ID,
        "auto.offset.reset": offset_reset,
        "enable.auto.commit": False,  # we commit only AFTER the DB write succeeds
    })


def _build_deserializers() -> dict:
    """One JSONDeserializer per topic, validating against the same schema files
    the producer registered. Maps topic name -> deserializer."""
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.json_schema import JSONDeserializer

    for k in ("SCHEMA_REGISTRY_URL", "SCHEMA_REGISTRY_API_KEY", "SCHEMA_REGISTRY_API_SECRET"):
        if not os.environ.get(k):
            sys.exit(f"Missing {k} in .env. See streaming/README.md (Phase 1 step 2).")
    client = SchemaRegistryClient({
        "url": os.environ["SCHEMA_REGISTRY_URL"],
        "basic.auth.user.info": f"{os.environ['SCHEMA_REGISTRY_API_KEY']}:{os.environ['SCHEMA_REGISTRY_API_SECRET']}",
    })
    out = {}
    for feed_name, (_url, topic, _builder, schema_file) in FEEDS.items():
        schema_str = (SCHEMA_DIR / schema_file).read_text()
        out[topic] = JSONDeserializer(schema_str, schema_registry_client=client)
    return out


# --------------------------------------------------------------------------- #
# Record -> row tuples
# --------------------------------------------------------------------------- #
def _status_row(rec: dict) -> tuple:
    snapshot_at = datetime.fromtimestamp(rec["snapshot_ts"], tz=timezone.utc)
    return (
        rec["station_id"], rec["snapshot_ts"], snapshot_at, rec.get("last_reported"),
        rec.get("num_bikes_available"), rec.get("num_ebikes_available"),
        rec.get("num_bikes_disabled"), rec.get("num_docks_available"),
        rec.get("num_docks_disabled"), rec.get("is_installed"),
        rec.get("is_renting"), rec.get("is_returning"),
    )


def _info_row(rec: dict) -> tuple:
    return (
        rec["station_id"], rec["snapshot_ts"], rec.get("name"), rec.get("short_name"),
        rec.get("lat"), rec.get("lon"), rec.get("capacity"), rec.get("region_id"),
    )


# --------------------------------------------------------------------------- #
# Postgres writes
# --------------------------------------------------------------------------- #
def _ensure_partitions(cur, status_rows: list[tuple]) -> None:
    """Create a monthly partition for each distinct snapshot month in the batch."""
    months = {(r[2].year, r[2].month) for r in status_rows}  # r[2] = snapshot_at
    for year, month in months:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        part = f"cabi_station_status_{year}_{month:02d}"
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS raw.{part} PARTITION OF raw.cabi_station_status "
            f"FOR VALUES FROM (%s) TO (%s)",
            (start, end),
        )


def _flush(conn, consumer, status_buf: list, info_buf: list) -> tuple[int, int]:
    from psycopg2.extras import execute_values

    if not status_buf and not info_buf:
        return (0, 0)
    with conn.cursor() as cur:
        if info_buf:
            execute_values(
                cur,
                "INSERT INTO raw.cabi_station_information "
                "(station_id, snapshot_ts, name, short_name, lat, lon, capacity, region_id) "
                "VALUES %s "
                "ON CONFLICT (station_id) DO UPDATE SET "
                "  snapshot_ts = EXCLUDED.snapshot_ts, name = EXCLUDED.name, "
                "  short_name = EXCLUDED.short_name, lat = EXCLUDED.lat, lon = EXCLUDED.lon, "
                "  capacity = EXCLUDED.capacity, region_id = EXCLUDED.region_id, "
                "  _ingested_at = now() "
                "WHERE EXCLUDED.snapshot_ts >= raw.cabi_station_information.snapshot_ts",
                info_buf,
            )
        if status_buf:
            _ensure_partitions(cur, status_buf)
            execute_values(
                cur,
                "INSERT INTO raw.cabi_station_status "
                "(station_id, snapshot_ts, snapshot_at, last_reported, num_bikes_available, "
                " num_ebikes_available, num_bikes_disabled, num_docks_available, "
                " num_docks_disabled, is_installed, is_renting, is_returning) VALUES %s",
                status_buf,
            )
    conn.commit()                          # DB write durable first...
    consumer.commit(asynchronous=False)    # ...then advance Kafka offsets (at-least-once)
    n = (len(status_buf), len(info_buf))
    status_buf.clear()
    info_buf.clear()
    return n


# --------------------------------------------------------------------------- #
def _handle_signal(signum, _frame):
    global _running
    _running = False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drain", action="store_true",
                        help="Exit once the backlog is consumed (instead of running forever).")
    parser.add_argument("--from", dest="offset_reset", choices=["earliest", "latest"],
                        default="earliest", help="Where a NEW consumer group starts (default: earliest).")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    _load_dotenv()
    consumer = _build_consumer(args.offset_reset)
    deserializers = _build_deserializers()
    conn = _connect_pg()
    consumer.subscribe([TOPIC_STATUS, TOPIC_INFORMATION])

    from confluent_kafka.serialization import SerializationContext, MessageField

    status_buf: list[tuple] = []
    info_buf: list[tuple] = []
    total_status = total_info = skipped = 0
    empty_polls = 0

    print(f"consumer '{GROUP_ID}' started (offset_reset={args.offset_reset}, drain={args.drain}). Ctrl-C to stop.")
    try:
        while _running:
            msg = consumer.poll(1.0)
            if msg is None:
                s, i = _flush(conn, consumer, status_buf, info_buf)
                total_status += s
                total_info += i
                empty_polls += 1
                if args.drain and (total_status + total_info) > 0 and empty_polls >= 3:
                    break
                continue
            empty_polls = 0
            if msg.error():
                print(f"kafka: {msg.error()}", file=sys.stderr)
                continue
            try:
                rec = deserializers[msg.topic()](
                    msg.value(), SerializationContext(msg.topic(), MessageField.VALUE)
                )
            except Exception:
                skipped += 1  # legacy/plain-JSON messages that aren't in wire format
                continue
            if msg.topic() == TOPIC_STATUS:
                status_buf.append(_status_row(rec))
            else:
                info_buf.append(_info_row(rec))
            if len(status_buf) + len(info_buf) >= BATCH_SIZE:
                s, i = _flush(conn, consumer, status_buf, info_buf)
                total_status += s
                total_info += i
    finally:
        s, i = _flush(conn, consumer, status_buf, info_buf)
        total_status += s
        total_info += i
        consumer.close()
        conn.close()
        print(f"\nstopped. wrote {total_status} status rows, {total_info} information rows; "
              f"skipped {skipped} undecodable messages.")


if __name__ == "__main__":
    main()
