-- ============================================================
--  file:       dbt/models/marts/dim_ad_slots.sql
--  purpose:    conformed ad slot dimension keyed by slot position
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per ad slot position.
with slt as (
    select
        s.slot_position
        , s.typical_duration_sec
        , s.avg_completion_rate
        , s.avg_viewability
    from {{ ref('stg_ad_slots') }} as s
)
select
    {{ dbt_utils.generate_surrogate_key(['slt.slot_position']) }} as slot_key
    , slt.slot_position
    , slt.typical_duration_sec
    , slt.avg_completion_rate
    , slt.avg_viewability
from slt
