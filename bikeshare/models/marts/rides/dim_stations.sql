-- One row per unique station observed in ride data.
--
-- A given station can appear as both a start and an end across many rides.
-- We union both sides, then take the most recent observation per station_id
-- (in case a station's name or coordinates were corrected between ingests).
--
-- Powers the dashboard's "Unique Stations" count and provides a clean lookup
-- for any chart that wants to enrich a station_id with its name + coordinates.

WITH trips AS (

    -- All systems via the intermediate layer. The composite (system, station_id)
    -- uniqueness is what makes this work multi-system — Capital Bikeshare and
    -- Citi Bike could both have a station_id 'HB202' (they don't, but could).
    SELECT * FROM {{ ref('int_rides__unioned') }}

),

starts AS (

    SELECT
        system,
        start_station_id   AS station_id,
        start_station_name AS station_name,
        start_lat          AS lat,
        start_lng          AS lng,
        started_at         AS observed_at
    FROM trips
    WHERE start_station_id IS NOT NULL

),

ends AS (

    SELECT
        system,
        end_station_id     AS station_id,
        end_station_name   AS station_name,
        end_lat            AS lat,
        end_lng            AS lng,
        ended_at           AS observed_at
    FROM trips
    WHERE end_station_id IS NOT NULL

),

all_observations AS (

    SELECT * FROM starts
    UNION ALL
    SELECT * FROM ends

),

ranked AS (

    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY system, station_id
            ORDER BY observed_at DESC
        ) AS recency_rank
    FROM all_observations

)

SELECT
    system,
    station_id,
    station_name,
    lat,
    lng,
    observed_at AS most_recent_observation_at
FROM ranked
WHERE recency_rank = 1
