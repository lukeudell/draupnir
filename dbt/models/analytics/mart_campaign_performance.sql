-- ============================================================
--  file:       dbt/models/analytics/mart_campaign_performance.sql
--  purpose:    dashboard-ready campaign pacing with campaign and advertiser context
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per campaign per day.
with campaign_daily as (
    select
        f.campaign_key
        , f.date_key
        , f.impressions_served
        , f.revenue_usd
        , f.cumulative_spend
        , f.elapsed_days
        , f.total_budget_usd
        , f.flight_days
        , f.budget_pacing_ratio
        , f.pacing_status
    from {{ ref('fct_campaign_daily') }} as f
)
, dim_campaigns as (
    select
        c.campaign_key
        , c.advertiser_key
        , c.campaign_name
        , c.frequency_cap
    from {{ ref('dim_campaigns') }} as c
)
, dim_advertisers as (
    select
        a.advertiser_key
        , a.company_name
        , a.industry_vertical
    from {{ ref('dim_advertisers') }} as a
)
select
    cd.campaign_key
    , dc.campaign_name
    , da.company_name
    , da.industry_vertical
    , cd.date_key
    , cd.elapsed_days
    , cd.impressions_served as impressions
    , cd.revenue_usd
    , cd.cumulative_spend
    , cd.total_budget_usd
    , cd.flight_days
    , cd.budget_pacing_ratio
    , cd.pacing_status
    , dc.frequency_cap
from campaign_daily as cd
inner join dim_campaigns as dc
    on cd.campaign_key = dc.campaign_key
inner join dim_advertisers as da
    on dc.advertiser_key = da.advertiser_key
