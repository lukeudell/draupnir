-- ============================================================
--  file:       dbt/models/staging/stg_ad_slots.sql
--  purpose:    stage ad break reference rates, 1:1 with source
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per ad slot position.
select
    s.slot_position
    , s.typical_duration_sec
    , s.avg_completion_rate
    , s.avg_viewability
from {{ source('ads_staging', 'ad_slots') }} as s
