-- Staging: light cleanup of raw.cabi_station_status_5min (Flink windowed flow).
--
-- One row per station per time window. Mechanical only — tag system, expose
-- columns. The interesting work (windowed aggregation) already happened in Flink.

WITH source AS (

    SELECT * FROM {{ source('capitalbikeshare_live', 'station_status_5min') }}

),

renamed AS (

    SELECT
        station_id,
        window_start,
        window_end,
        num_snapshots,
        avg_bikes,
        min_bikes,
        max_bikes,
        bikes_swing,                       -- max - min within the window (churn proxy)
        _ingested_at,
        'capitalbikeshare'::text           AS system

    FROM source

)

SELECT * FROM renamed
