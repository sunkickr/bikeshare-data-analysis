-- DC Census tract ride aggregates — one row per tract per month.
--
-- Uses Census TIGER 2023 tract boundaries (~179 tracts). Unlike the
-- neighbourhood and cluster models, population data here is exact — tracts
-- are the native ACS unit, so no spatial interpolation is needed.
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

station_tract AS (

    SELECT station_id, tract_geoid
    FROM {{ ref('dc_station_census_tracts') }}

),

tract_meta AS (

    SELECT tract_geoid, tract_name, area_km2, centroid_lat, centroid_lng
    FROM {{ ref('dc_census_tracts') }}

),

tract_pop AS (

    SELECT tract_geoid, population, households, median_household_income
    FROM {{ ref('dc_census_tract_population') }}

),

arrivals AS (

    SELECT
        st.tract_geoid,
        DATE_TRUNC('month', r.started_at)::date AS started_month,
        COUNT(*)                                  AS arrival_rides
    FROM {{ ref('fct_rides') }} r
    JOIN {{ ref('dc_station_census_tracts') }} st ON r.end_station_id = st.station_id
    WHERE r.system = 'capitalbikeshare'
    GROUP BY st.tract_geoid, DATE_TRUNC('month', r.started_at)::date

),

station_count AS (

    SELECT tract_geoid, COUNT(*) AS station_count
    FROM {{ ref('dc_station_census_tracts') }}
    GROUP BY tract_geoid

),

aggregated AS (

    SELECT
        st.tract_geoid,
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
    JOIN station_tract st ON r.start_station_id = st.station_id
    GROUP BY st.tract_geoid, r.started_month

)

SELECT
    a.tract_geoid,
    t.tract_name,
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
    t.area_km2,
    t.centroid_lat,
    t.centroid_lng,
    p.population,
    p.households,
    p.median_household_income

FROM aggregated a
JOIN tract_meta t           ON a.tract_geoid = t.tract_geoid
LEFT JOIN tract_pop p       ON a.tract_geoid = p.tract_geoid
LEFT JOIN arrivals arr      ON a.tract_geoid = arr.tract_geoid
                           AND a.started_month = arr.started_month
LEFT JOIN station_count stc ON a.tract_geoid = stc.tract_geoid
ORDER BY a.started_month DESC, a.total_rides DESC
