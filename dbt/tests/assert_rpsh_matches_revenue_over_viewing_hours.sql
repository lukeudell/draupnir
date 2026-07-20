-- ============================================================
--  file:       dbt/tests/assert_rpsh_matches_revenue_over_viewing_hours.sql
--  purpose:    RPSH must divide ad revenue by content viewing hours
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-14]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-20
-- ============================================================
-- depends_on: {{ ref('mart_platform_health') }}
-- depends_on: {{ ref('fct_viewing_sessions') }}
-- depends_on: {{ ref('fct_ad_impressions') }}
-- why: RPSH is the metric the catalog calls the one that balances monetisation
-- against experience, and it was documented for a long time while being
-- computed nowhere. The specific way it could go wrong now is subtle: the
-- impression grain carries view_duration_sec, which is ad watch time, and using
-- it here would produce a plausible number that is really a completion-weighted
-- eCPM. This recomputes the ratio from the two facts independently, so the
-- denominator has to stay content viewing time.
with revenue_by_day as (
    select
        i.date_key
        , sum(i.revenue_usd) as revenue_usd
    from {{ ref('fct_ad_impressions') }} as i
    group by i.date_key
)
, hours_by_day as (
    select
        s.date_key
        , sum(s.watch_seconds) / 3600.0 as viewing_hours
    from {{ ref('fct_viewing_sessions') }} as s
    group by s.date_key
)
, expected as (
    select
        r.date_key
        , round(r.revenue_usd / nullif(h.viewing_hours, 0), 4) as expected_rpsh
    from revenue_by_day as r
    inner join hours_by_day as h
        on r.date_key = h.date_key
)
select
    p.date_key
    , p.revenue_per_subscriber_hour
    , e.expected_rpsh
from {{ ref('mart_platform_health') }} as p
inner join expected as e
    on p.date_key = e.date_key
where p.revenue_per_subscriber_hour is distinct from e.expected_rpsh
