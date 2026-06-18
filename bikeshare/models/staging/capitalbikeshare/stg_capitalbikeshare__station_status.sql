-- Staging: light cleanup of raw.cabi_station_status (live availability snapshots).
--
-- One row per station per ~60s poll. Mechanical only — cast/rename/tag, no joins,
-- no business logic (that's marts' job). This view is the single place downstream
-- models look for live status data; if the raw shape changes, only this changes.

WITH source AS (

    SELECT * FROM {{ source('capitalbikeshare_live', 'station_status') }}

),

renamed AS (

    SELECT
        station_id,
        snapshot_ts,
        snapshot_at,

        -- The station's own self-report time, distinct from the feed snapshot
        -- time. We time-bucket analytics on snapshot_at (when WE observed the
        -- system), not last_reported_at — same spirit as bucketing rides on
        -- started_at rather than a station-clock value.
        to_timestamp(last_reported)        AS last_reported_at,

        num_bikes_available,
        num_ebikes_available,
        num_bikes_disabled,
        num_docks_available,
        num_docks_disabled,
        is_installed,
        is_renting,
        is_returning,

        _ingested_at,

        -- Every staging model tags its system so downstream marts stay
        -- system-agnostic (same convention as the trips staging models).
        'capitalbikeshare'::text           AS system

    FROM source

)

SELECT * FROM renamed
