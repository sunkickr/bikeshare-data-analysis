-- Windowed availability flow per station — the Flink-derived (Phase 4) fact.
--
-- One row per station per window, enriched with station name/geo from
-- dim_cabi_stations. bikes_swing (max - min within the window) is a churn proxy:
-- high swing = lots of pickups/returns; 0 = a quiet station that window.
--
-- Materialized as a table (small: one row per station per window). Not incremental
-- yet — the volume is low and the consumer upserts on (station_id, window_start),
-- so a full rebuild is cheap and idempotent.

WITH flow AS (

    SELECT * FROM {{ ref('stg_capitalbikeshare__station_status_5min') }}

)

SELECT
    f.system,
    f.station_id,
    d.station_name,
    d.short_name,
    d.lat,
    d.lon,
    d.capacity,

    f.window_start,
    f.window_end,
    f.window_start::date                AS window_date,

    f.num_snapshots,
    f.avg_bikes,
    f.min_bikes,
    f.max_bikes,
    f.bikes_swing

FROM flow f
LEFT JOIN {{ ref('dim_cabi_stations') }} d USING (system, station_id)
