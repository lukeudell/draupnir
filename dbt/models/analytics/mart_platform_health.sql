-- ============================================================
--  file:       dbt/models/analytics/mart_platform_health.sql
--  purpose:    daily platform KPIs: fill rate, eCPM, engagement
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per day.
with requests as (
    select
        r.request_id
        , r.request_timestamp
    from {{ ref('stg_ad_requests') }} as r
)
, dim_date as (
    select
        d.date_key
        , d.full_date
    from {{ ref('dim_date_ads') }} as d
)
, impressions as (
    select
        i.date_key
        , i.subscriber_key
        , i.revenue_usd
        , i.is_viewable
        , i.completed
    from {{ ref('fct_ad_impressions') }} as i
)
, daily_requests as (
    select
        dd.date_key
        , count(*) as total_requests
    from requests as req
    inner join dim_date as dd
        on cast(to_char(req.request_timestamp, 'YYYYMMDD') as integer) = dd.date_key
    group by dd.date_key
)
, daily_impressions as (
    select
        imp.date_key
        , count(*) as total_impressions
        , count(*) filter (where imp.completed) as completed_impressions
        , count(*) filter (where imp.is_viewable) as viewable_impressions
        , sum(imp.revenue_usd) as total_revenue_usd
        , count(distinct imp.subscriber_key) as unique_subscribers
    from impressions as imp
    group by imp.date_key
)
, sessions as (
    select
        s.date_key
        , s.watch_seconds
    from {{ ref('fct_viewing_sessions') }} as s
)
, daily_viewing as (
    select
        ses.date_key
        , sum(ses.watch_seconds) / 3600.0 as viewing_hours
    from sessions as ses
    group by ses.date_key
)
-- noqa: disable=ST06
-- why: ST06 wants plain columns before calculated ones, which would put
-- full_date ahead of date_key. date_key is the grain of this model and leads
-- the column list; it is a coalesce only because the requests and impressions
-- CTEs are joined with a full outer join and either side can be missing.
select
    coalesce(dr.date_key, di.date_key) as date_key
    , dd.full_date
    , coalesce(dr.total_requests, 0) as total_requests
    , coalesce(di.total_impressions, 0) as total_impressions
    , round(
        100.0 * coalesce(di.total_impressions, 0) / nullif(dr.total_requests, 0)
        , 1
    ) as fill_rate_pct
    , round(
        coalesce(di.total_revenue_usd, 0) / nullif(di.total_impressions, 0) * 1000
        , 2
    ) as ecpm_usd
    , round(
        100.0 * coalesce(di.completed_impressions, 0) / nullif(di.total_impressions, 0)
        , 1
    ) as completion_rate_pct
    , round(
        100.0 * coalesce(di.viewable_impressions, 0) / nullif(di.total_impressions, 0)
        , 1
    ) as viewability_rate_pct
    , coalesce(di.total_revenue_usd, 0) as total_revenue_usd
    , coalesce(di.unique_subscribers, 0) as unique_subscribers
    , round(coalesce(dv.viewing_hours, 0), 1) as viewing_hours
    -- Revenue per subscriber hour. The denominator is content viewing time
    -- from fct_viewing_sessions, not ad watch time: dividing by ad seconds
    -- would be a completion-weighted eCPM wearing a different name. Null on a
    -- day with no recorded viewing, which is undefined rather than zero.
    , round(
        coalesce(di.total_revenue_usd, 0) / nullif(dv.viewing_hours, 0)
        , 4
    ) as revenue_per_subscriber_hour
from daily_requests as dr
full outer join daily_impressions as di
    on dr.date_key = di.date_key
inner join dim_date as dd
    on coalesce(dr.date_key, di.date_key) = dd.date_key
left join daily_viewing as dv
    on coalesce(dr.date_key, di.date_key) = dv.date_key
order by dd.full_date
