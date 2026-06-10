-- Staging model: light cleanup of raw.citibike_trips.
--
-- Structurally identical to stg_capitalbikeshare__trips except:
--   * Reads from the citibike source (different raw table)
--   * Tags rows with system = 'citibike'
--
-- Keeping the two staging models separate (rather than DRY-ing them up with
-- a macro) is a deliberate choice: when one source's schema diverges, only
-- that source's staging file needs to change. Premature deduplication of
-- structurally similar staging files is a common dbt project mistake.

WITH source AS (

    SELECT * FROM {{ source('citibike', 'trips') }}

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

        _ingested_at,
        _source_file,

        'citibike'::text             AS system

    FROM source
    WHERE ride_id IS NOT NULL

)

SELECT * FROM renamed
