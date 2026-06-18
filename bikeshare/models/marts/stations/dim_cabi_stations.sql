-- One row per live CABI station: latest name, coordinates, and capacity.
--
-- This is the live-side analogue of dim_stations (which is TRIP-derived and
-- system-agnostic). They are intentionally separate dimensions:
--   * dim_stations       — keyed on the numeric trip station_id, DC + NYC.
--   * dim_cabi_stations  — keyed on the GBFS UUID, CABI only, and the only
--                          source with authoritative capacity + live coords.
-- short_name is the bridge to the trip world (live.short_name == trips.station_id)
-- if the two are ever joined — but that's a future feature, not used here.

WITH info AS (

    SELECT * FROM {{ ref('stg_capitalbikeshare__station_information') }}

),

ranked AS (

    -- The staging table is already one row per station (raw is upserted), but
    -- rank defensively so this holds even if duplicates ever appear.
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY system, station_id
            ORDER BY snapshot_at DESC
        ) AS recency_rank
    FROM info

)

SELECT
    system,
    station_id,
    short_name,
    station_name,
    lat,
    lon,
    capacity,
    region_id,
    snapshot_at AS most_recent_observation_at
FROM ranked
WHERE recency_rank = 1
