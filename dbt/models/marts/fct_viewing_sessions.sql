-- ============================================================
--  file:       dbt/models/marts/fct_viewing_sessions.sql
--  purpose:    the viewing-hours denominator for revenue per subscriber hour
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-20
-- ============================================================
-- Grain: one row per viewing session.
--
-- This exists so that revenue per subscriber hour has a real denominator.
-- The impression grain already carries view_duration_sec, but that is how long
-- an *ad* was watched; dividing revenue by it would be a completion-weighted
-- eCPM under another name. Content viewing time is a different quantity and
-- needs its own fact.
with ses as (
    select
        s.session_id
        , s.subscriber_id
        , s.content_id
        , s.session_start
        , s.device
        , s.watch_seconds
        , s.deepest_slot
        , s.ad_requests
    from {{ ref('stg_viewing_sessions') }} as s
)
, sub as (
    select
        d.subscriber_key
        , d.subscriber_id
    from {{ ref('dim_subscribers') }} as d
)
, cnt as (
    select
        d.content_key
        , d.content_id
    from {{ ref('dim_content') }} as d
)
, dt as (
    select d.date_key
    from {{ ref('dim_date_ads') }} as d
)
select
    ses.session_id
    , sub.subscriber_key
    , cnt.content_key
    , dt.date_key
    , ses.watch_seconds
    , ses.deepest_slot
    , ses.ad_requests
    , ses.device
    , ses.session_start
from ses
inner join sub
    on ses.subscriber_id = sub.subscriber_id
inner join cnt
    on ses.content_id = cnt.content_id
inner join dt
    on cast(to_char(ses.session_start, 'YYYYMMDD') as integer) = dt.date_key
