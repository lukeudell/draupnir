-- ============================================================
--  file:       dbt/models/staging/stg_viewing_sessions.sql
--  purpose:    stage viewing sessions, 1:1 with source
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-20
-- ============================================================
-- Grain: one row per viewing session.
select
    s.session_id
    , s.subscriber_id
    , s.content_id
    , s.session_start
    , s.device
    , s.watch_seconds
    , s.deepest_slot
    , s.ad_requests
from {{ source('ads_staging', 'viewing_sessions') }} as s
