-- DC Census block group ride aggregates — one row per block group per month.
--
-- Uses Census TIGER 2023 block group boundaries (~450 block groups in DC).
-- Block groups are the finest Census geography with ACS income/population data.
-- Population data is exact — no spatial interpolation needed.
--
-- Only Capital Bikeshare rides are included (system = 'capitalbikeshare').

WITH rides AS (

    SELECT
        start_station_id,
        member_casual,
        rideable_type,
        duration_seconds,
        started_dow,
        is_round_trip,
        is_night_owl,
        DATE_TRUNC('month', started_at)::date AS started_month
    FROM {{ ref('fct_rides') }}
    WHERE system = 'capitalbikeshare'

),

station_bg AS (

    SELECT station_id, bg_geoid
    FROM {{ ref('dc_station_block_groups') }}

),

bg_meta AS (

    SELECT bg_geoid, bg_name, area_km2, centroid_lat, centroid_lng
    FROM {{ ref('dc_block_groups') }}

),

bg_pop AS (

    SELECT bg_geoid, population, households, median_household_income
    FROM {{ ref('dc_block_group_population') }}

),

arrivals AS (

    SELECT
        sb.bg_geoid,
        DATE_TRUNC('month', r.started_at)::date AS started_month,
        COUNT(*)                                  AS arrival_rides
    FROM {{ ref('fct_rides') }} r
    JOIN {{ ref('dc_station_block_groups') }} sb ON r.end_station_id = sb.station_id
    WHERE r.system = 'capitalbikeshare'
    GROUP BY sb.bg_geoid, DATE_TRUNC('month', r.started_at)::date

),

station_count AS (

    SELECT bg_geoid, COUNT(*) AS station_count
    FROM {{ ref('dc_station_block_groups') }}
    GROUP BY bg_geoid

),

aggregated AS (

    SELECT
        sb.bg_geoid,
        r.started_month,
        COUNT(*)                                                       AS total_rides,
        COUNT(*) FILTER (WHERE r.member_casual = 'member')            AS member_rides,
        COUNT(*) FILTER (WHERE r.member_casual = 'casual')            AS casual_rides,
        COUNT(*) FILTER (WHERE r.started_dow BETWEEN 1 AND 5)        AS weekday_rides,
        COUNT(*) FILTER (WHERE r.started_dow IN (6, 7))              AS weekend_rides,
        COUNT(*) FILTER (WHERE r.rideable_type = 'electric_bike')    AS electric_rides,
        COUNT(*) FILTER (WHERE r.is_round_trip)                       AS round_trip_rides,
        COUNT(*) FILTER (WHERE r.is_night_owl)                        AS night_owl_rides,
        SUM(r.duration_seconds)                                        AS total_duration_seconds
    FROM rides r
    JOIN station_bg sb ON r.start_station_id = sb.station_id
    GROUP BY sb.bg_geoid, r.started_month

)

SELECT
    a.bg_geoid,
    b.bg_name,
    a.started_month,
    a.total_rides,
    a.member_rides,
    a.casual_rides,
    a.weekday_rides,
    a.weekend_rides,
    a.electric_rides,
    a.round_trip_rides,
    a.night_owl_rides,
    a.total_duration_seconds,
    COALESCE(arr.arrival_rides, 0) AS arrival_rides,
    stc.station_count,

    -- Static context — repeats per month, used by dashboard to avoid extra joins
    b.area_km2,
    b.centroid_lat,
    b.centroid_lng,
    p.population,
    p.households,
    p.median_household_income

FROM aggregated a
JOIN bg_meta b              ON a.bg_geoid = b.bg_geoid
LEFT JOIN bg_pop p          ON a.bg_geoid = p.bg_geoid
LEFT JOIN arrivals arr      ON a.bg_geoid = arr.bg_geoid
                           AND a.started_month = arr.started_month
LEFT JOIN station_count stc ON a.bg_geoid = stc.bg_geoid
ORDER BY a.started_month DESC, a.total_rides DESC
