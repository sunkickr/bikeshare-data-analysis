-- Raw landing tables for the live CABI stream (Phase 2).
-- Idempotent: safe to re-run. Monthly partitions are created at runtime by consumer.py.

CREATE SCHEMA IF NOT EXISTS raw;

-- Slowly-changing dimension: latest attributes per station. Upserted on station_id.
-- lat/lon live here only (the stable source of truth, per the dashboard's geo rule).
CREATE TABLE IF NOT EXISTS raw.cabi_station_information (
    station_id   text PRIMARY KEY,
    snapshot_ts  bigint NOT NULL,
    name         text,
    short_name   text,
    lat          double precision,
    lon          double precision,
    capacity     integer,
    region_id    text,
    _ingested_at timestamptz NOT NULL DEFAULT now()
);

-- High-volume fact: append-only availability snapshots, partitioned by month on
-- snapshot_at. Partitioned tables can't have a PK that excludes the partition key,
-- and this is an append log, so it has none. "today's map" prunes to one partition.
CREATE TABLE IF NOT EXISTS raw.cabi_station_status (
    station_id           text        NOT NULL,
    snapshot_ts          bigint      NOT NULL,
    snapshot_at          timestamptz NOT NULL,
    last_reported        bigint,
    num_bikes_available  integer,
    num_ebikes_available integer,
    num_bikes_disabled   integer,
    num_docks_available  integer,
    num_docks_disabled   integer,
    is_installed         smallint,
    is_renting           smallint,
    is_returning         smallint,
    _ingested_at         timestamptz NOT NULL DEFAULT now()
) PARTITION BY RANGE (snapshot_at);

-- Flink-derived windowed flow (Phase 4): one row per station per time window,
-- computed by a Confluent Flink SQL standing query and landed by consumer.py.
-- Low volume (one row per station per window), so not partitioned. PK makes
-- re-consumption idempotent.
CREATE TABLE IF NOT EXISTS raw.cabi_station_status_5min (
    station_id    text      NOT NULL,
    window_start  timestamp NOT NULL,
    window_end    timestamp NOT NULL,
    num_snapshots integer,
    avg_bikes     integer,
    min_bikes     integer,
    max_bikes     integer,
    bikes_swing   integer,
    _ingested_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (station_id, window_start)
);
