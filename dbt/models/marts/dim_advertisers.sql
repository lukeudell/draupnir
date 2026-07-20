-- ============================================================
--  file:       dbt/models/marts/dim_advertisers.sql
--  purpose:    conformed advertiser dimension for campaign rollups
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per advertiser.
with adv as (
    select
        a.advertiser_id
        , a.company_name
        , a.industry_vertical
        , a.spend_tier
        , a.country
    from {{ ref('stg_advertisers') }} as a
)
select
    {{ dbt_utils.generate_surrogate_key(['adv.advertiser_id']) }} as advertiser_key
    , adv.advertiser_id
    , adv.company_name
    , adv.industry_vertical
    , adv.spend_tier
    , adv.country
from adv
