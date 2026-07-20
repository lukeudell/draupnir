-- ============================================================
--  file:       dbt/models/marts/fct_campaign_daily.sql
--  purpose:    daily campaign delivery and budget pacing fact for the monitor
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per campaign per day.
--
-- Pacing here is budget delivery: spend to date against the share of the flight
-- elapsed. It answers "will this campaign deliver what the advertiser bought?".
-- An earlier version divided today's spend by the campaign's own average day,
-- which answers "was today unusual?" and, because the baseline moves with the
-- spend, can never show a campaign systematically under-delivering.
with imp as (
    select
        i.campaign_key
        , i.subscriber_key
        , i.date_key
        , i.revenue_usd
        , i.is_viewable
        , i.completed
    from {{ ref('fct_ad_impressions') }} as i
)
, cmp as (
    select
        c.campaign_key
        , c.total_budget_usd
        , c.flight_days
        , c.flight_start
    from {{ ref('dim_campaigns') }} as c
)
, dt as (
    select
        d.date_key
        , d.full_date
    from {{ ref('dim_date_ads') }} as d
)
, agg as (
    select
        imp.campaign_key
        , imp.date_key
        , count(*) as impressions_served
        , count(*) filter (where imp.is_viewable) as impressions_viewable
        , count(*) filter (where imp.completed) as impressions_completed
        , sum(imp.revenue_usd) as revenue_usd
        , count(distinct imp.subscriber_key) as unique_subscribers
    from imp
    group by
        imp.campaign_key
        , imp.date_key
)
, cum as (
    select
        agg.campaign_key
        , agg.date_key
        , agg.impressions_served
        , agg.impressions_viewable
        , agg.impressions_completed
        , agg.revenue_usd
        , agg.unique_subscribers
        , cmp.total_budget_usd
        , cmp.flight_days
        , sum(agg.revenue_usd) over (
            partition by agg.campaign_key
            order by agg.date_key
        ) as cumulative_spend
        -- why: elapsed time is a property of the calendar and the flight start,
        -- never of whether anything was delivered. Counting delivery days
        -- instead would under-count elapsed time for a campaign with gaps,
        -- biasing the ratio upward and hiding exactly the under-delivery this
        -- metric exists to surface.
        , (dt.full_date - cmp.flight_start) + 1 as elapsed_days
    from agg
    inner join cmp
        on agg.campaign_key = cmp.campaign_key
    inner join dt
        on agg.date_key = dt.date_key
)
select
    cum.campaign_key
    , cum.date_key
    , cum.impressions_served
    , cum.impressions_viewable
    , cum.impressions_completed
    , cum.revenue_usd
    , cum.unique_subscribers
    , cum.total_budget_usd
    , cum.cumulative_spend
    , cum.elapsed_days
    , cum.flight_days
    -- Published definition: cumulative_spend / (elapsed_days / flight_days * budget).
    -- Flight progress is capped at 1.0 because once the flight has ended the
    -- expected delivery is the whole budget and no more.
    , round(
        cum.cumulative_spend
        / nullif(
            cum.total_budget_usd * least(
                cum.elapsed_days::numeric / nullif(cum.flight_days, 0), 1.0
            )
            , 0
        )
        , 3
    ) as budget_pacing_ratio
    -- why: classified from the rounded ratio, so the label can never disagree
    -- with the number printed beside it. A null ratio means there was no budget
    -- or no flight to divide by, which is unknown rather than on pace.
    , case
        when round(
            cum.cumulative_spend
            / nullif(
                cum.total_budget_usd * least(
                    cum.elapsed_days::numeric / nullif(cum.flight_days, 0), 1.0
                )
                , 0
            )
            , 3
        ) is null then 'UNKNOWN'
        when round(
            cum.cumulative_spend
            / nullif(
                cum.total_budget_usd * least(
                    cum.elapsed_days::numeric / nullif(cum.flight_days, 0), 1.0
                )
                , 0
            )
            , 3
        ) < 0.9 then 'UNDER_PACING'
        when round(
            cum.cumulative_spend
            / nullif(
                cum.total_budget_usd * least(
                    cum.elapsed_days::numeric / nullif(cum.flight_days, 0), 1.0
                )
                , 0
            )
            , 3
        ) > 1.1 then 'OVER_PACING'
        else 'ON_PACE'
    end as pacing_status
from cum
