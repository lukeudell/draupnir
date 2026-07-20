-- ============================================================
--  file:       dbt/models/analytics/mart_content_monetization.sql
--  purpose:    which content genres drive ad revenue and viewer engagement
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per genre per day.
with impressions as (
    select
        i.content_key
        , i.date_key
        , i.revenue_usd
        , i.view_duration_sec
    from {{ ref('fct_ad_impressions') }} as i
)
, dim_content as (
    select
        c.content_key
        , c.genre
    from {{ ref('dim_content') }} as c
)
select
    dc.genre
    , imp.date_key
    , count(*) as impressions
    , sum(imp.revenue_usd) as revenue_usd
    , round(avg(imp.view_duration_sec)::numeric, 1) as avg_view_duration_sec
from impressions as imp
inner join dim_content as dc
    on imp.content_key = dc.content_key
group by
    dc.genre
    , imp.date_key
