-- ============================================================
--  file:       dbt/tests/assert_hhi_matches_squared_shares.sql
--  purpose:    the concentration index must be the sum of squared shares
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-14]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- depends_on: {{ ref('mart_advertiser_concentration') }}
-- depends_on: {{ ref('mart_advertiser_summary') }}
-- why: HHI is a single number carrying a regulatory threshold, so a quiet error
-- in it changes a published risk verdict with nothing else looking wrong. This
-- recomputes it the long way the app used to, dividing shares by 100 and
-- scaling by 10000, which is algebraically the same as squaring the percentages
-- but arrives by a different route. Agreement between the two is what makes the
-- simplification in the model safe.
with recomputed as (
    select sum(power(a.revenue_share_pct / 100.0, 2)) * 10000 as expected_hhi
    from {{ ref('mart_advertiser_summary') }} as a
)
select
    c.hhi
    , r.expected_hhi
from {{ ref('mart_advertiser_concentration') }} as c
cross join recomputed as r
where abs(c.hhi - r.expected_hhi) > 0.1
