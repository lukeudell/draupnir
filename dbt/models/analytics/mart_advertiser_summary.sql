-- ============================================================
--  file:       dbt/models/analytics/mart_advertiser_summary.sql
--  purpose:    per-advertiser spend, efficiency and platform revenue share
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per advertiser.
with impressions as (
    select
        i.advertiser_key
        , i.campaign_key
        , i.revenue_usd
        , i.is_viewable
        , i.completed
    from {{ ref('fct_ad_impressions') }} as i
)
, dim_advertisers as (
    select
        a.advertiser_key
        , a.company_name
        , a.industry_vertical
        , a.spend_tier
    from {{ ref('dim_advertisers') }} as a
)
, platform_total as (
    select sum(imp.revenue_usd) as total_platform_spend
    from impressions as imp
)
, advertiser_agg as (
    select
        da.advertiser_key
        , da.company_name
        , da.industry_vertical
        , da.spend_tier
        , sum(imp.revenue_usd) as total_spend
        , count(*) as total_impressions
        , round(
            sum(imp.revenue_usd) / nullif(count(*), 0) * 1000
            , 2
        ) as ecpm
        , round(
            100.0 * count(*) filter (where imp.completed) / nullif(count(*), 0)
            , 1
        ) as completion_rate_pct
        , round(
            100.0 * count(*) filter (where imp.is_viewable) / nullif(count(*), 0)
            , 1
        ) as viewability_rate_pct
        , count(distinct imp.campaign_key) as campaign_count
    from impressions as imp
    inner join dim_advertisers as da
        on imp.advertiser_key = da.advertiser_key
    group by
        da.advertiser_key
        , da.company_name
        , da.industry_vertical
        , da.spend_tier
)
select
    aa.advertiser_key
    , aa.company_name
    , aa.industry_vertical
    , aa.spend_tier
    , aa.total_spend
    , aa.total_impressions
    , aa.ecpm
    , aa.completion_rate_pct
    , aa.viewability_rate_pct
    , aa.campaign_count
    , round(
        100.0 * aa.total_spend / nullif(pt.total_platform_spend, 0)
        , 2
    ) as revenue_share_pct
from advertiser_agg as aa
cross join platform_total as pt
