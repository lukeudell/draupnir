-- ============================================================
--  file:       dbt/models/analytics/mart_frequency_analysis.sql
--  purpose:    campaign-level frequency cap violation rates
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per campaign.
with impressions as (
    select
        i.subscriber_key
        , i.campaign_key
    from {{ ref('fct_ad_impressions') }} as i
)
, dim_campaigns as (
    select
        c.campaign_key
        , c.campaign_name
        , c.frequency_cap
    from {{ ref('dim_campaigns') }} as c
)
, subscriber_campaign as (
    select
        imp.subscriber_key
        , imp.campaign_key
        , count(*) as total_impressions_to_subscriber
    from impressions as imp
    group by
        imp.subscriber_key
        , imp.campaign_key
)
, with_cap as (
    select
        sc.subscriber_key
        , sc.campaign_key
        , dc.campaign_name
        , sc.total_impressions_to_subscriber
        , dc.frequency_cap
        -- A violation is actual impressions strictly above the configured cap
        , sc.total_impressions_to_subscriber > dc.frequency_cap as is_cap_exceeded
    from subscriber_campaign as sc
    inner join dim_campaigns as dc
        on sc.campaign_key = dc.campaign_key
)
select
    wc.campaign_key
    , wc.campaign_name
    , wc.frequency_cap
    , count(*) as total_subscribers
    , count(*) filter (where wc.is_cap_exceeded) as subscribers_exceeding_cap
    , sum(
        case
            when wc.is_cap_exceeded
                then wc.total_impressions_to_subscriber - wc.frequency_cap
            else 0
        end
    ) as total_violations
    , round(
        100.0 * count(*) filter (where wc.is_cap_exceeded) / nullif(count(*), 0)
        , 1
    ) as violation_rate_pct
    , round(
        avg(wc.total_impressions_to_subscriber)::numeric
        , 1
    ) as avg_frequency
from with_cap as wc
group by
    wc.campaign_key
    , wc.campaign_name
    , wc.frequency_cap
