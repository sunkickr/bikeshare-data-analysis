-- Current availability per station — the model the live map reads.
--
-- "Current" = the most recent snapshot per station in fct_cabi_station_status,
-- enriched with geo/capacity from dim_cabi_stations (the coordinate source of
-- truth — never aggregate fct coordinates, same rule the dashboard uses for
-- dim_stations).
--
-- FRESHNESS CAVEAT: this is only as recent as the last `dbt build`. For a truly
-- minute-fresh map we either rebuild this often or read raw directly — that
-- freshness decision belongs to Phase 5 / Flink (Phase 4).

WITH latest AS (

    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY system, station_id
            ORDER BY snapshot_at DESC
        ) AS rn
    FROM {{ ref('fct_cabi_station_status') }}

)

SELECT
    s.system,
    s.station_id,
    d.station_name,
    d.short_name,
    d.lat,
    d.lon,
    d.capacity,

    s.num_bikes_available,
    s.num_ebikes_available,
    s.num_docks_available,

    -- Fill ratio for the map's color scale (0 = empty, 1 = full). NULL-safe.
    ROUND(s.num_bikes_available::numeric / NULLIF(d.capacity, 0), 3) AS fill_ratio,

    s.is_renting,
    s.snapshot_at AS as_of

FROM latest s
LEFT JOIN {{ ref('dim_cabi_stations') }} d USING (system, station_id)
WHERE s.rn = 1
