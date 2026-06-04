-- DC Neighborhood Cluster ride aggregates — one row per cluster per month.
--
-- Identical structure to agg_rides_by_neighborhood but uses the 39 official
-- DC planning clusters instead of OSM neighbourhood polygons. Allows the
-- dashboard to compare the two boundary definitions side-by-side.

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

station_cluster AS (

    SELECT station_id, cluster_id
    FROM {{ ref('dc_station_clusters') }}

),

cluster_meta AS (

    SELECT cluster_id, cluster_display_name, area_km2, centroid_lat, centroid_lng
    FROM {{ ref('dc_clusters') }}

),

cluster_pop AS (

    SELECT cluster_id, population, households, median_household_income
    FROM {{ ref('dc_cluster_population') }}

),

arrivals AS (

    SELECT
        sc.cluster_id,
        DATE_TRUNC('month', r.started_at)::date AS started_month,
        COUNT(*)                                  AS arrival_rides
    FROM {{ ref('fct_rides') }} r
    JOIN {{ ref('dc_station_clusters') }} sc ON r.end_station_id = sc.station_id
    WHERE r.system = 'capitalbikeshare'
    GROUP BY sc.cluster_id, DATE_TRUNC('month', r.started_at)::date

),

aggregated AS (

    SELECT
        sc.cluster_id,
        r.started_month,
        COUNT(*)                                                       AS total_rides,
        COUNT(*) FILTER (WHERE r.member_casual = 'member')            AS member_rides,
        COUNT(*) FILTER (WHERE r.member_casual = 'casual')            AS casual_rides,
        COUNT(*) FILTER (WHERE r.started_dow BETWEEN 1 AND 5)        AS weekday_rides,
        COUNT(*) FILTER (WHERE r.started_dow IN (6, 7))              AS weekend_rides,
        SUM(r.duration_seconds)                                        AS total_duration_seconds
    FROM rides r
    JOIN station_cluster sc ON r.start_station_id = sc.station_id
    GROUP BY sc.cluster_id, r.started_month

)

SELECT
    a.cluster_id,
    m.cluster_display_name,
    a.started_month,
    a.total_rides,
    a.member_rides,
    a.casual_rides,
    a.weekday_rides,
    a.weekend_rides,
    a.total_duration_seconds,
    COALESCE(arr.arrival_rides, 0) AS arrival_rides,
    m.area_km2,
    m.centroid_lat,
    m.centroid_lng,
    p.population,
    p.households,
    p.median_household_income

FROM aggregated a
JOIN cluster_meta m    ON a.cluster_id = m.cluster_id
LEFT JOIN cluster_pop p   ON a.cluster_id = p.cluster_id
LEFT JOIN arrivals arr     ON a.cluster_id = arr.cluster_id
                          AND a.started_month = arr.started_month
ORDER BY a.started_month DESC, a.total_rides DESC
