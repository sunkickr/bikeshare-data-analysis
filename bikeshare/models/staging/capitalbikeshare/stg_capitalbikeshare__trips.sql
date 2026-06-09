-- Staging model: light cleanup of raw.capitalbikeshare_trips.
--
-- Staging-layer rules of thumb (dbt convention):
--   * Cast types (text -> timestamp / numeric).
--   * Rename to consistent snake_case (already snake_case here).
--   * Drop or filter obviously-bad rows (null ride_id).
--   * NO business logic, NO joins, NO aggregations — that's marts' job.
--
-- One staging model per source table. This view is the *only* place downstream
-- models look for Capital Bikeshare ride data; if the raw schema changes, this
-- file is the one place that has to change.

WITH source AS (

    SELECT * FROM {{ source('capitalbikeshare', 'trips') }}

),

renamed AS (

    SELECT
        ride_id,
        rideable_type,
        started_at::timestamp        AS started_at,
        ended_at::timestamp          AS ended_at,
        start_station_name,
        start_station_id,
        end_station_name,
        end_station_id,
        start_lat::numeric           AS start_lat,
        start_lng::numeric           AS start_lng,
        end_lat::numeric             AS end_lat,
        end_lng::numeric             AS end_lng,
        member_casual,

        -- Provenance columns — useful for debugging and incremental loads.
        _ingested_at,
        _source_file,

        -- Future-proofing for multi-system support: every row carries which
        -- bikeshare system it came from. When we add Citi Bike (NYC), its
        -- staging model will hardcode 'citibike' here, and downstream marts
        -- can union them without ambiguity.
        'capitalbikeshare'::text     AS system

    FROM source
    WHERE ride_id IS NOT NULL

),

-- Source files occasionally republish the same ride_id across two adjacent
-- monthly exports (boundary rides that start late in one month and end in the
-- next). Keep one row per ride — the most recently loaded copy — so this view's
-- stated grain (one row per ride) actually holds. This mirrors how fct_rides
-- resolves the same collision via its delete+insert on the latest load.
deduped AS (

    SELECT *
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY ride_id
                ORDER BY _ingested_at DESC
            ) AS _row_num
        FROM renamed
    ) ranked
    WHERE _row_num = 1

)

SELECT
    ride_id,
    rideable_type,
    started_at,
    ended_at,
    start_station_name,
    start_station_id,
    end_station_name,
    end_station_id,
    start_lat,
    start_lng,
    end_lat,
    end_lng,
    member_casual,
    _ingested_at,
    _source_file,
    system
FROM deduped
