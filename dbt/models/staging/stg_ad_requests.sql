-- ============================================================
--  file:       dbt/models/staging/stg_ad_requests.sql
--  purpose:    stage raw ad impression opportunities, 1:1 with source
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per ad request.
select
    s.request_id
    , s.session_id
    , s.subscriber_id
    , s.content_id
    , s.slot_position
    , s.request_timestamp
    , s.device
    , s.was_filled
from {{ source('ads_staging', 'ad_requests') }} as s
