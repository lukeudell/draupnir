-- ============================================================
--  file:       dbt/models/staging/stg_advertisers.sql
--  purpose:    stage raw advertiser accounts, 1:1 with source
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per advertiser.
select
    s.advertiser_id
    , s.company_name
    , s.industry_vertical
    , s.spend_tier
    , s.country
from {{ source('ads_staging', 'advertisers') }} as s
