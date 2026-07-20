-- ============================================================
--  file:       dbt/tests/assert_impressions_reconcile_with_filled_requests.sql
--  purpose:    the was_filled flag and the impression count must agree
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-14]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- depends_on: {{ ref('stg_ad_requests') }}
-- depends_on: {{ ref('fct_ad_impressions') }}
-- why: the project carries two independent definitions of "filled". The request
-- grain has a was_filled boolean, and mart_platform_health derives fill rate
-- from a join count against impressions instead. Nothing compared them, so a
-- generator or join change could move the headline fill rate while every
-- not_null test stayed green. A filled request must produce exactly one
-- impression, so the two counts are the same number reached two ways.
with filled_requests as (
    select count(*) as request_count
    from {{ ref('stg_ad_requests') }} as r
    where r.was_filled
)
, served_impressions as (
    select count(*) as impression_count
    from {{ ref('fct_ad_impressions') }}
)
select
    fr.request_count
    , si.impression_count
from filled_requests as fr
cross join served_impressions as si
where fr.request_count <> si.impression_count
