-- Pre-aggregated daily ride metrics, sliced by the dimensions the dashboard
-- splits on most often (member_casual, rideable_type).
--
-- Why pre-aggregate? `fct_rides` has 260K rows for one month. With twelve
-- months, that's 3M+ row scans every time a dashboard chart asks "rides per
-- day." Pre-aggregating to one row per (date, system, member_casual,
-- rideable_type) cuts that by orders of magnitude.
--
-- This model also demonstrates a multi-step DAG: it depends on fct_rides,
-- which depends on stg_capitalbikeshare__trips, which depends on the source.

WITH rides AS (

    SELECT * FROM {{ ref('fct_rides') }}

)

SELECT
    started_date,
    system,
    member_casual,
    rideable_type,

    COUNT(*)                                           AS total_rides,
    SUM(duration_seconds) / 3600.0                     AS total_hours_on_bike,
    AVG(duration_minutes)                              AS avg_ride_minutes,
    MIN(duration_minutes)                              AS shortest_ride_minutes,
    MAX(duration_minutes)                              AS longest_ride_minutes,
    SUM(CASE WHEN is_night_owl THEN 1 ELSE 0 END)      AS night_owl_rides,
    SUM(CASE WHEN is_round_trip THEN 1 ELSE 0 END)     AS round_trip_rides

FROM rides
GROUP BY 1, 2, 3, 4
