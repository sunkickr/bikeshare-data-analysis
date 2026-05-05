-- One row per ride, with derived columns the dashboard needs.
--
-- INCREMENTAL: each `dbt run` only processes rows that have arrived since the
-- last run, identified by _ingested_at. The unique_key='ride_id' + delete+insert
-- strategy makes the operation idempotent if a load is replayed.
--
-- To rebuild from scratch: `dbt run -s fct_rides+ --full-refresh`
{{ config(
    materialized='incremental',
    unique_key='ride_id',
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
) }}

WITH trips AS (

    -- All bikeshare systems, unioned in the intermediate layer. Adding a
    -- new system means editing int_rides__unioned, not this file.
    SELECT * FROM {{ ref('int_rides__unioned') }}

    {% if is_incremental() %}
    -- Only on incremental runs (not the initial build, not --full-refresh):
    -- restrict to rows that landed AFTER the latest one already in fct_rides.
    -- {{ this }} compiles to the fully-qualified name of THIS model's table.
    WHERE _ingested_at > (
        SELECT COALESCE(MAX(_ingested_at), '1900-01-01'::timestamp)
        FROM {{ this }}
    )
    {% endif %}

),

derived AS (

    SELECT
        -- Identity & dimensions
        ride_id,
        system,
        rideable_type,
        member_casual,
        start_station_id,
        start_station_name,
        end_station_id,
        end_station_name,
        start_lat,
        start_lng,
        end_lat,
        end_lng,

        -- Raw timestamps
        started_at,
        ended_at,

        -- Derived time slices used by the dashboard.
        -- The dashboard filters by started_at — that's the canonical "when did
        -- the ride happen" — even though ended_at could fall in another month.
        started_at::date                                   AS started_date,
        EXTRACT(hour FROM started_at)::int                 AS started_hour,
        EXTRACT(isodow FROM started_at)::int               AS started_dow,    -- 1=Mon..7=Sun
        TO_CHAR(started_at, 'Day')                         AS started_dow_name,
        DATE_TRUNC('month', started_at)::date              AS started_month,

        -- Duration. Stored both ways: seconds (precise math), minutes (display).
        EXTRACT(epoch FROM (ended_at - started_at))::int   AS duration_seconds,
        ROUND(EXTRACT(epoch FROM (ended_at - started_at)) / 60.0, 2)
                                                           AS duration_minutes,

        -- Booleans for direct use in dashboard filters.
        (EXTRACT(hour FROM started_at) BETWEEN 0 AND 4)    AS is_night_owl,
        (start_station_id = end_station_id)                AS is_round_trip,
        (start_station_id IS DISTINCT FROM end_station_id) AS is_between_stations,

        -- Provenance
        _ingested_at,
        _source_file

    FROM trips

),

cleaned AS (

    -- Drop physically impossible rides. We do this here, not in staging,
    -- because "ended_at < started_at" is a business-logic judgment, not a
    -- type cast. Staging stays mechanical; marts make the rules.
    SELECT *
    FROM derived
    WHERE ended_at >= started_at

)

SELECT * FROM cleaned
