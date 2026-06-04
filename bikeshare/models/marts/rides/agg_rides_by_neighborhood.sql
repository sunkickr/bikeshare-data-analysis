-- DC neighbourhood ride aggregates — one row per neighbourhood per month.
--
-- Static neighbourhood metadata (area, population) repeats each month;
-- derived metrics (per-resident, per-km², member %) are intentionally
-- omitted here and computed at query time so multi-month aggregations
-- stay mathematically correct.
--
-- Only Capital Bikeshare rides are included (system = 'capitalbikeshare').

WITH rides AS (

    SELECT
        start_station_id,
        member_casual,
        duration_seconds,
        started_dow,
        DATE_TRUNC('month', started_at)::date AS started_month
    FROM {{ ref('fct_rides') }}
    WHERE system = 'capitalbikeshare'

),

station_nbhd AS (

    SELECT station_id, neighborhood_name
    FROM {{ ref('dc_station_neighborhoods') }}

),

nbhd_meta AS (

    SELECT neighborhood_name, area_km2, centroid_lat, centroid_lng
    FROM {{ ref('dc_neighborhoods') }}

),

nbhd_pop AS (

    SELECT neighborhood_name, population, households, median_household_income
    FROM {{ ref('dc_neighborhood_population') }}

),

arrivals AS (

    SELECT
        sn.neighborhood_name,
        DATE_TRUNC('month', r.started_at)::date AS started_month,
        COUNT(*)                                  AS arrival_rides
    FROM {{ ref('fct_rides') }} r
    JOIN {{ ref('dc_station_neighborhoods') }} sn ON r.end_station_id = sn.station_id
    WHERE r.system = 'capitalbikeshare'
    GROUP BY sn.neighborhood_name, DATE_TRUNC('month', r.started_at)::date

),

aggregated AS (

    SELECT
        sn.neighborhood_name,
        r.started_month,
        COUNT(*)                                                       AS total_rides,
        COUNT(*) FILTER (WHERE r.member_casual = 'member')            AS member_rides,
        COUNT(*) FILTER (WHERE r.member_casual = 'casual')            AS casual_rides,
        COUNT(*) FILTER (WHERE r.started_dow BETWEEN 1 AND 5)        AS weekday_rides,
        COUNT(*) FILTER (WHERE r.started_dow IN (6, 7))              AS weekend_rides,
        SUM(r.duration_seconds)                                        AS total_duration_seconds
    FROM rides r
    JOIN station_nbhd sn ON r.start_station_id = sn.station_id
    GROUP BY sn.neighborhood_name, r.started_month

)

SELECT
    a.neighborhood_name,
    a.started_month,
    a.total_rides,
    a.member_rides,
    a.casual_rides,
    a.weekday_rides,
    a.weekend_rides,
    a.total_duration_seconds,
    COALESCE(arr.arrival_rides, 0) AS arrival_rides,

    -- Static context — repeats per month, used by dashboard to avoid extra joins
    m.area_km2,
    m.centroid_lat,
    m.centroid_lng,
    p.population,
    p.households,
    p.median_household_income

FROM aggregated a
JOIN nbhd_meta  m ON a.neighborhood_name = m.neighborhood_name
LEFT JOIN nbhd_pop p   ON a.neighborhood_name = p.neighborhood_name
LEFT JOIN arrivals arr  ON a.neighborhood_name = arr.neighborhood_name
                       AND a.started_month = arr.started_month
ORDER BY a.started_month DESC, a.total_rides DESC
