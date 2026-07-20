-- ============================================================
--  file:       dbt/models/staging/stg_ad_impressions.sql
--  purpose:    stage raw served ad impressions, 1:1 with source
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per delivered ad impression.
select
    s.impression_id
    , s.request_id
    , s.campaign_id
    , s.advertiser_id
    , s.subscriber_id
    , s.content_id
    , s.slot_position
    , s.device
    , s.bid_price_usd
    , s.revenue_usd
    , s.is_viewable
    , s.completed
    , s.view_duration_sec
    , s.impression_timestamp
from {{ source('ads_staging', 'ad_impressions') }} as s
