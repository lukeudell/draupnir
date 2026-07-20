-- ============================================================
--  file:       dbt/models/marts/dim_campaigns.sql
--  purpose:    conformed campaign dimension carrying the advertiser key
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per campaign.
with cmp as (
    select
        c.campaign_id
        , c.advertiser_id
        , c.campaign_name
        , c.objective
        , c.daily_budget_usd
        , c.total_budget_usd
        , c.flight_start
        , c.flight_end
        , c.flight_days
        , c.frequency_cap
        , c.pacing_goal
        , c.status
    from {{ ref('stg_campaigns') }} as c
)
, adv as (
    select
        a.advertiser_key
        , a.advertiser_id
    from {{ ref('dim_advertisers') }} as a
)
select
    {{ dbt_utils.generate_surrogate_key(['cmp.campaign_id']) }} as campaign_key
    , cmp.campaign_id
    , adv.advertiser_key
    , cmp.campaign_name
    , cmp.objective
    , cmp.daily_budget_usd
    , cmp.total_budget_usd
    , cmp.flight_start
    , cmp.flight_end
    , cmp.flight_days
    , cmp.frequency_cap
    , cmp.pacing_goal
    , cmp.status
from cmp
inner join adv
    on cmp.advertiser_id = adv.advertiser_id
