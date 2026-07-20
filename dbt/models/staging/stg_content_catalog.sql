-- ============================================================
--  file:       dbt/models/staging/stg_content_catalog.sql
--  purpose:    stage raw content catalog titles, 1:1 with source
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per content title.
select
    s.content_id
    , s.title
    , s.content_type
    , s.genre
    , s.avg_episode_minutes
    , s.maturity_rating
from {{ source('ads_staging', 'content_catalog') }} as s
