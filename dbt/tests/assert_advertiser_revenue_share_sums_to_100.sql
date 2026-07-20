-- ============================================================
--  file:       dbt/tests/assert_advertiser_revenue_share_sums_to_100.sql
--  purpose:    advertiser revenue shares must account for all platform revenue
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-14]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- depends_on: {{ ref('mart_advertiser_summary') }}
-- why: revenue_share_pct is computed per advertiser against a cross-joined
-- platform total, and the app squares it to produce the HHI concentration
-- figure. If the denominator ever drifts from the numerator's population, for
-- example by filtering advertisers in one CTE and not the other, every share is
-- wrong by the same factor and the HHI moves with no other symptom. The shares
-- summing to 100 is what makes them shares.
with share_total as (
    select sum(a.revenue_share_pct) as total_pct
    from {{ ref('mart_advertiser_summary') }} as a
)
select st.total_pct
from share_total as st
-- tolerance: each share is rounded to two decimals before summing, so with one
-- row per advertiser the accumulated rounding error is bounded well inside 1pp.
where abs(st.total_pct - 100.0) > 1.0
