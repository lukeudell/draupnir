-- ============================================================
--  file:       dbt/models/staging/stg_campaigns.sql
--  purpose:    stage raw campaigns with budgets and flight dates, 1:1 with source
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per campaign.
select
    s.campaign_id
    , s.advertiser_id
    , s.campaign_name
    , s.objective
    , s.daily_budget_usd
    , s.total_budget_usd
    , s.flight_start
    , s.flight_end
    , s.flight_days
    , s.frequency_cap
    , s.pacing_goal
    , s.status
from {{ source('ads_staging', 'campaigns') }} as s
