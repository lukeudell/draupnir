-- ============================================================
--  file:       dbt/models/marts/fct_ad_impressions.sql
--  purpose:    star fact joining each impression to its conformed keys
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per delivered ad impression.
with imp as (
    select
        i.impression_id
        , i.request_id
        , i.campaign_id
        , i.advertiser_id
        , i.subscriber_id
        , i.content_id
        , i.slot_position
        , i.device
        , i.bid_price_usd
        , i.revenue_usd
        , i.is_viewable
        , i.completed
        , i.view_duration_sec
        , i.impression_timestamp
    from {{ ref('stg_ad_impressions') }} as i
)
, cmp as (
    select
        c.campaign_key
        , c.campaign_id
    from {{ ref('dim_campaigns') }} as c
)
, adv as (
    select
        a.advertiser_key
        , a.advertiser_id
    from {{ ref('dim_advertisers') }} as a
)
, sub as (
    select
        s.subscriber_key
        , s.subscriber_id
    from {{ ref('dim_subscribers') }} as s
)
, cnt as (
    select
        c.content_key
        , c.content_id
    from {{ ref('dim_content') }} as c
)
, slt as (
    select
        s.slot_key
        , s.slot_position
    from {{ ref('dim_ad_slots') }} as s
)
, dt as (
    select d.date_key
    from {{ ref('dim_date_ads') }} as d
)
select
    imp.impression_id
    , imp.request_id
    , cmp.campaign_key
    , adv.advertiser_key
    , sub.subscriber_key
    , cnt.content_key
    , slt.slot_key
    , dt.date_key
    , imp.bid_price_usd
    , imp.revenue_usd
    , imp.is_viewable
    , imp.completed
    , imp.view_duration_sec
    , imp.device
    , imp.impression_timestamp
from imp
inner join cmp
    on imp.campaign_id = cmp.campaign_id
inner join adv
    on imp.advertiser_id = adv.advertiser_id
inner join sub
    on imp.subscriber_id = sub.subscriber_id
inner join cnt
    on imp.content_id = cnt.content_id
inner join slt
    on imp.slot_position = slt.slot_position
inner join dt
    on cast(to_char(imp.impression_timestamp, 'YYYYMMDD') as integer) = dt.date_key
