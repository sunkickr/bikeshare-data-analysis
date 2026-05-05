-- Intermediate model: union all bikeshare ride staging models into a single
-- conformed shape that downstream marts can treat as "all rides, regardless
-- of system."
--
-- Adding a new bikeshare system is a 3-step pattern:
--   1. Create models/staging/<system>/stg_<system>__trips.sql with the same
--      output columns as the existing staging models, tagged with the new
--      system value.
--   2. Add a UNION ALL clause below.
--   3. (Optional) Update accepted_values tests on the system column.
--
-- Note: the column list is implicit via SELECT *. This works because each
-- staging model is contracted (via _<system>__models.yml) to expose the same
-- columns. If a future system has extra columns, normalize them in that
-- system's staging model — never in this intermediate model.

WITH capitalbikeshare AS (

    SELECT * FROM {{ ref('stg_capitalbikeshare__trips') }}

),

citibike AS (

    SELECT * FROM {{ ref('stg_citibike__trips') }}

)

SELECT * FROM capitalbikeshare
UNION ALL
SELECT * FROM citibike
