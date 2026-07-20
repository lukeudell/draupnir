-- ============================================================
--  file:       dbt/tests/assert_pacing_ratio_matches_published_formula.sql
--  purpose:    the shipped pacing ratio must be the published pacing ratio
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-14]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- depends_on: {{ ref('fct_campaign_daily') }}
-- why: this is the metric the application is named after, and the published
-- definition is budget delivery: spend to date against the share of the flight
-- elapsed. The model previously computed today's spend against the campaign's
-- own average day, which is a different question with a different baseline and
-- averages to 1.0 by construction. Recomputing the published formula from the
-- model's own emitted columns is what stops the two drifting apart again.
--
-- Flight progress is capped at 1.0: once the flight has ended, the expected
-- delivery is the whole budget, not more than it.
with recomputed as (
    select
        f.campaign_key
        , f.date_key
        , f.budget_pacing_ratio
        , round(
            f.cumulative_spend
            / nullif(
                f.total_budget_usd * least(
                    f.elapsed_days::numeric / nullif(f.flight_days, 0), 1.0
                )
                , 0
            )
            , 3
        ) as expected_ratio
    from {{ ref('fct_campaign_daily') }} as f
)
select
    r.campaign_key
    , r.date_key
    , r.budget_pacing_ratio
    , r.expected_ratio
from recomputed as r
where r.budget_pacing_ratio is distinct from r.expected_ratio
