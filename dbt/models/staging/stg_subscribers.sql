-- ============================================================
--  file:       dbt/models/staging/stg_subscribers.sql
--  purpose:    stage raw subscriber accounts, 1:1 with source
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per subscriber.
select
    s.subscriber_id
    , s.subscription_tier
    , s.signup_date
    , s.region
    , s.device_primary
    , s.age_band
from {{ source('ads_staging', 'subscribers') }} as s
