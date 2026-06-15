# streaming/ — GBFS → Kafka → local Postgres

Live CABI station pipeline for the auto-updating dashboard map.
Full plan: [`ideas/live-station-map-plan.md`](../ideas/live-station-map-plan.md).

```
GBFS feeds ──producer.py──► Confluent Cloud topics ──consumer.py──► local Postgres ──dbt──► dashboard
            (data plane)       (Schema Registry)      (data plane)
```

**Control plane vs data plane:** the `confluent` CLI (below) creates the cluster,
topics, and keys — run by hand, a few times. `producer.py` / `consumer.py` use the
Kafka **client API** to move messages — they run continuously.

---

## Verify the GBFS half now (no account, no installs)

`--dry-run` uses only the Python stdlib:

```bash
.venv/bin/python streaming/producer.py --dry-run
```

You should see ~847 records each for `status` and `information`. ✅ confirmed working.

---

## Phase 0 — Confluent foundations (control plane, CLI)

This part is yours to do (account creation + key custody can't be automated).

1. **Sign up** for Confluent Cloud (free $400 / 30-day credits): https://confluent.cloud/signup

2. **Install the CLI** (macOS):
   ```bash
   brew install confluentinc/tap/cli
   confluent version
   ```

3. **Log in + create a Basic cluster** (cheapest; pick a nearby region):
   ```bash
   confluent login --save
   confluent environment list                      # note the env id
   confluent environment use <env-id>
   confluent kafka cluster create cabi --cloud aws --region us-east-1 --type basic
   confluent kafka cluster use <cluster-id>
   ```

4. **Create the two topics:**
   ```bash
   confluent kafka topic create cabi.station_status
   confluent kafka topic create cabi.station_information
   ```

5. **Mint an API key** for the cluster (this is the data-plane credential):
   ```bash
   confluent api-key create --resource <cluster-id>
   ```

6. **Smoke test by hand** (prove produce/consume works before any code):
   ```bash
   echo '{"hello":"world"}' | confluent kafka topic produce cabi.station_status
   confluent kafka topic consume cabi.station_status --from-beginning   # Ctrl-C to stop
   ```

7. **Save credentials to `.env`** (repo root; already gitignored):
   ```
   BOOTSTRAP_SERVERS=<bootstrap server from `confluent kafka cluster describe`>
   KAFKA_API_KEY=<key from step 5>
   KAFKA_API_SECRET=<secret from step 5>
   ```

---

## Phase 1 — Producer (data plane)

```bash
.venv/bin/pip install -r streaming/requirements.txt
.venv/bin/python streaming/producer.py --once     # one poll → topics, then exit
.venv/bin/python streaming/producer.py            # poll forever, every 60s
```

Confirm with the CLI consumer from Phase 0. Next: register the JSON Schemas in
`streaming/schemas/` to Schema Registry (Phase 1 step 2).

## Phase 2 — Consumer → local Postgres (coming next)

`consumer.py` will read both topics and write to `raw.cabi_station_status`
(month-partitioned, append) and `raw.cabi_station_information` (upsert latest).
