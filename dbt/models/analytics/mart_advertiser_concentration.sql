-- ============================================================
--  file:       dbt/models/analytics/mart_advertiser_concentration.sql
--  purpose:    single-advertiser revenue concentration risk, as an HHI
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row for the whole observation window.
--
-- The Herfindahl-Hirschman index is the concentration measure the DOJ applies
-- to merger review, borrowed here to quantify how exposed platform revenue is
-- to a single advertiser leaving. Its thresholds come with it: below 1500 is
-- diversified, 1500 to 2500 moderate, above 2500 concentrated.
--
-- This was previously computed in the Streamlit app, which made the project's
-- most interesting metric untested and unavailable to anything that was not the
-- dashboard. Note the arithmetic: HHI is defined as the sum of squared percent
-- shares, so squaring revenue_share_pct directly is the whole calculation.
-- Dividing by 100 and multiplying by 10000, as the app did, is the same number
-- reached by a longer route.
with shares as (
    select
        a.advertiser_key
        , a.revenue_share_pct
    from {{ ref('mart_advertiser_summary') }} as a
)
, scored as (
    select
        sum(power(shares.revenue_share_pct, 2)) as hhi
        , count(*) as advertiser_count
        , max(shares.revenue_share_pct) as top_advertiser_share_pct
    from shares
)
-- noqa: disable=ST06
-- why: ST06 wants plain columns before calculated ones, which would put
-- advertiser_count ahead of hhi. The index is what this model exists to
-- produce and leads the column list; the counts beside it are supporting
-- detail for reading it.
select
    round(scored.hhi, 1) as hhi
    , case
        when scored.hhi < 1500 then 'DIVERSIFIED'
        when scored.hhi < 2500 then 'MODERATE'
        else 'CONCENTRATED'
    end as concentration_band
    , scored.advertiser_count
    , round(scored.top_advertiser_share_pct, 2) as top_advertiser_share_pct
from scored
