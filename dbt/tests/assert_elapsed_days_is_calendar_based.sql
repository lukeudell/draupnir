-- ============================================================
--  file:       dbt/tests/assert_elapsed_days_is_calendar_based.sql
--  purpose:    elapsed_days must count calendar days, not delivery days
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-14]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- depends_on: {{ ref('fct_campaign_daily') }}
-- depends_on: {{ ref('dim_date_ads') }}
-- depends_on: {{ ref('dim_campaigns') }}
-- why: elapsed_days was a row_number() over the days a campaign actually served
-- impressions, so a campaign with delivery gaps under-counted the time elapsed.
-- That biases the pacing ratio upward, which is precisely the direction that
-- hides under-delivery: the metric would report a campaign on pace while it
-- quietly missed days. Elapsed time is a property of the calendar and the
-- flight start, never of whether anything was delivered.
with actual as (
    select
        f.campaign_key
        , f.date_key
        , f.elapsed_days
        , (dd.full_date - dc.flight_start) + 1 as calendar_elapsed_days
    from {{ ref('fct_campaign_daily') }} as f
    inner join {{ ref('dim_date_ads') }} as dd
        on f.date_key = dd.date_key
    inner join {{ ref('dim_campaigns') }} as dc
        on f.campaign_key = dc.campaign_key
)
select
    a.campaign_key
    , a.date_key
    , a.elapsed_days
    , a.calendar_elapsed_days
from actual as a
where a.elapsed_days <> a.calendar_elapsed_days
