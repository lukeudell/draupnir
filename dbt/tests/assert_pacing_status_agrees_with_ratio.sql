-- ============================================================
--  file:       dbt/tests/assert_pacing_status_agrees_with_ratio.sql
--  purpose:    the status label must follow from the ratio it describes
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-14]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- depends_on: {{ ref('fct_campaign_daily') }}
-- why: pacing_status used to recompute its own division four times rather than
-- reading the ratio column, and it classified from the unrounded value while
-- the ratio was rounded, so a boundary row could disagree with its own status.
-- Worse, its else branch was reachable only when the ratio was null, which made
-- a campaign with no baseline to divide by report ON_PACE rather than unknown.
-- A silent ON_PACE on missing data is the failure mode this whole project keeps
-- finding, so it gets a test.
with expected as (
    select
        f.campaign_key
        , f.date_key
        , f.budget_pacing_ratio
        , f.pacing_status
        , case
            when f.budget_pacing_ratio is null then 'UNKNOWN'
            when f.budget_pacing_ratio < 0.9 then 'UNDER_PACING'
            when f.budget_pacing_ratio > 1.1 then 'OVER_PACING'
            else 'ON_PACE'
        end as expected_status
    from {{ ref('fct_campaign_daily') }} as f
)
select
    e.campaign_key
    , e.date_key
    , e.budget_pacing_ratio
    , e.pacing_status
    , e.expected_status
from expected as e
where e.pacing_status <> e.expected_status
