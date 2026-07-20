-- ============================================================
--  file:       dbt/models/marts/dim_subscribers.sql
--  purpose:    conformed subscriber dimension for audience cuts
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per subscriber.
with sub as (
    select
        s.subscriber_id
        , s.subscription_tier
        , s.signup_date
        , s.region
        , s.device_primary
        , s.age_band
    from {{ ref('stg_subscribers') }} as s
)
select
    {{ dbt_utils.generate_surrogate_key(['sub.subscriber_id']) }} as subscriber_key
    , sub.subscriber_id
    , sub.subscription_tier
    , sub.signup_date
    , sub.region
    , sub.device_primary
    , sub.age_band
from sub
