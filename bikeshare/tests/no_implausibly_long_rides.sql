-- Singular data test: surface rides longer than 24 hours.
--
-- These are usually not real rides — they're bikes that weren't properly
-- returned (system auto-closed them at a default time) or instrumentation
-- artifacts. They distort the "longest ride" and "average ride" dashboard
-- metrics if left in.
--
-- We mark this as `severity: warn` (in the config block below) because the
-- raw data legitimately contains these — failing the build over them would
-- be too aggressive. A warning surfaces them in CI/logs so we know the
-- count is stable, and we can investigate when it spikes.

{{ config(severity = 'warn') }}

SELECT
    ride_id,
    started_at,
    ended_at,
    duration_seconds,
    duration_minutes
FROM {{ ref('fct_rides') }}
WHERE duration_seconds > 24 * 60 * 60
