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

aggregated AS (

    SELECT
        sn.neighborhood_name,
        r.started_month,
        COUNT(*)                                                       AS total_rides,
        COUNT(*) FILTER (WHERE r.member_casual = 'member')            AS member_rides,
        COUNT(*) FILTER (WHERE r.member_casual = 'casual')            AS casual_rides,
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
    a.total_duration_seconds,

    -- Static context — repeats per month, used by dashboard to avoid extra joins
    m.area_km2,
    m.centroid_lat,
    m.centroid_lng,
    p.population,
    p.households,
    p.median_household_income

FROM aggregated a
JOIN nbhd_meta  m ON a.neighborhood_name = m.neighborhood_name
LEFT JOIN nbhd_pop p ON a.neighborhood_name = p.neighborhood_name
ORDER BY a.started_month DESC, a.total_rides DESC
