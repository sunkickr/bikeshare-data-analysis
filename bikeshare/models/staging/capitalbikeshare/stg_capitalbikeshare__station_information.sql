-- Staging: light cleanup of raw.cabi_station_information (live station attributes).
--
-- One row per station (the raw table is upserted on station_id). Mechanical only.

WITH source AS (

    SELECT * FROM {{ source('capitalbikeshare_live', 'station_information') }}

),

renamed AS (

    SELECT
        station_id,
        short_name,                        -- numeric code; bridges to trips' station_id
        name                AS station_name,
        lat,
        lon,
        capacity,
        region_id,
        snapshot_ts,
        to_timestamp(snapshot_ts)          AS snapshot_at,
        _ingested_at,
        'capitalbikeshare'::text           AS system

    FROM source

)

SELECT * FROM renamed
