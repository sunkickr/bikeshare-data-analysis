-- Phase 4 — Confluent Flink SQL standing query.
--
-- Runs in Confluent Cloud (not via dbt/psql): paste into a Flink SQL workspace or
-- `confluent flink shell --compute-pool <lfcp-...> --database lkc-mv73wzw`.
-- Saved here so the streaming logic is version-controlled alongside everything else.
--
-- It reads the live status topic as a table, computes a tumbling-window aggregate
-- per station, and writes the result to a new Avro topic (cabi.station_status_5min),
-- which streaming/consumer.py then lands into raw.cabi_station_status_5min.
--
-- NOTE: the window is currently 1 MINUTE (fast feedback while learning); the topic
-- name keeps the _5min suffix. Widen INTERVAL to '5' MINUTES for the real cadence.
--
-- COST: this is a standing query — it runs (and the compute pool bills per minute)
-- until you `confluent flink statement delete <name>`. Tear down the pool when idle.

-- Read only messages produced from now on. The status topic still holds legacy
-- plain-JSON messages from before Schema Registry; Flink decodes via the registry
-- and would error on those, so we skip the backlog.
SET 'sql.tables.scan.startup.mode' = 'latest-offset';

-- CTAS: creates the sink topic + schema AND starts the continuous insert.
-- $rowtime is the Kafka record timestamp Confluent auto-attaches (with a watermark),
-- which is what makes event-time windowing work without parsing snapshot_ts.
CREATE TABLE `cabi.station_status_5min` AS
SELECT
    station_id,
    window_start,
    window_end,
    COUNT(*)                                              AS num_snapshots,
    AVG(num_bikes_available)                              AS avg_bikes,
    MIN(num_bikes_available)                              AS min_bikes,
    MAX(num_bikes_available)                              AS max_bikes,
    MAX(num_bikes_available) - MIN(num_bikes_available)   AS bikes_swing
FROM TABLE(
    TUMBLE(TABLE `cabi.station_status`, DESCRIPTOR(`$rowtime`), INTERVAL '1' MINUTE)
)
GROUP BY station_id, window_start, window_end;
