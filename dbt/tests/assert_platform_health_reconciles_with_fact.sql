-- ============================================================
--  file:       dbt/tests/assert_platform_health_reconciles_with_fact.sql
--  purpose:    the daily analytics rollup must sum back to its fact table
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-14]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- depends_on: {{ ref('mart_platform_health') }}
-- depends_on: {{ ref('fct_ad_impressions') }}
-- why: mart_platform_health is the table the app reads for every headline
-- number, and it is three joins away from the fact it summarizes. An aggregate
-- that quietly drops or duplicates rows still passes not_null on every column.
-- Totals are the cheapest invariant that catches it: whatever the grouping does,
-- the impression count and the revenue must survive the rollup unchanged.
with rollup as (
    select
        sum(h.total_impressions) as impression_count
        , round(sum(h.total_revenue_usd), 2) as revenue_usd
    from {{ ref('mart_platform_health') }} as h
)
, fact as (
    select
        count(*) as impression_count
        , round(sum(i.revenue_usd), 2) as revenue_usd
    from {{ ref('fct_ad_impressions') }} as i
)
select
    r.impression_count as rollup_impressions
    , f.impression_count as fact_impressions
    , r.revenue_usd as rollup_revenue
    , f.revenue_usd as fact_revenue
from rollup as r
cross join fact as f
-- tolerance on revenue only: the rollup rounds per day before summing, so the
-- two totals can differ by a fraction of a cent per day. Counts must be exact.
where
    r.impression_count <> f.impression_count
    or abs(r.revenue_usd - f.revenue_usd) > 1.00
