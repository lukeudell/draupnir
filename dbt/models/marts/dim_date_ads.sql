-- ============================================================
--  file:       dbt/models/marts/dim_date_ads.sql
--  purpose:    conformed date dimension shared by every ads fact
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per calendar date.
with dt as (
    select
        d.date_key
        , d.full_date
        , d.day_of_week
        , d.is_weekend
        , d.week_of_year
        , d.month_name
        , d.quarter
        , d.year
    from {{ source('ads_staging', 'dates_ads') }} as d
)
select
    dt.date_key
    , dt.full_date
    , dt.day_of_week
    , dt.is_weekend
    , dt.week_of_year
    , dt.month_name
    , dt.quarter
    , dt.year
from dt
