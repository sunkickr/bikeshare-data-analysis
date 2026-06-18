-- One row per station per ~60s snapshot — the live availability time series.
--
-- INCREMENTAL: each run only processes snapshots newer than what's already here,
-- watermarked on snapshot_at. unique_key=(station_id, snapshot_ts) + delete+insert
-- makes a replayed batch idempotent. This mirrors fct_rides' incremental pattern.
--
-- To rebuild from scratch: `dbt run -s fct_cabi_station_status+ --full-refresh`
{{ config(
    materialized='incremental',
    unique_key=['station_id', 'snapshot_ts'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
) }}

WITH status AS (

    SELECT * FROM {{ ref('stg_capitalbikeshare__station_status') }}

    {% if is_incremental() %}
    -- Only rows observed AFTER the latest snapshot already in this table.
    WHERE snapshot_at > (
        SELECT COALESCE(MAX(snapshot_at), '1900-01-01'::timestamptz)
        FROM {{ this }}
    )
    {% endif %}

),

deduped AS (

    -- One row per (station, snapshot). The consumer is at-least-once, so a
    -- replayed batch could re-deliver the same (station_id, snapshot_ts); keep
    -- the most recently ingested copy. Runs after the incremental filter, so on
    -- a normal run it only ranks the small new batch.
    SELECT *
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY station_id, snapshot_ts
                ORDER BY _ingested_at DESC
            ) AS _row_num
        FROM status
    ) ranked
    WHERE _row_num = 1

),

derived AS (

    SELECT
        station_id,
        system,
        snapshot_ts,
        snapshot_at,

        -- Time slices for analytics. Bucket on snapshot_at (our observation time).
        snapshot_at::date                                  AS snapshot_date,
        EXTRACT(hour FROM snapshot_at)::int                AS snapshot_hour,

        last_reported_at,

        num_bikes_available,
        num_ebikes_available,
        num_bikes_disabled,
        num_docks_available,
        num_docks_disabled,

        -- Active dock count = bikes you could take + docks you could return to.
        (num_bikes_available + num_docks_available)        AS docks_active,

        is_installed,
        is_renting,
        is_returning,

        _ingested_at

    FROM deduped

)

SELECT * FROM derived
