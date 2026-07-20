-- ============================================================
--  file:       dbt/models/marts/dim_content.sql
--  purpose:    conformed content dimension for the streaming catalog
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-04] [STD-13]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Grain: one row per content item.
with cnt as (
    select
        c.content_id
        , c.title
        , c.content_type
        , c.genre
        , c.avg_episode_minutes
        , c.maturity_rating
    from {{ ref('stg_content_catalog') }} as c
)
select
    {{ dbt_utils.generate_surrogate_key(['cnt.content_id']) }} as content_key
    , cnt.content_id
    , cnt.title
    , cnt.content_type
    , cnt.genre
    , cnt.avg_episode_minutes
    , cnt.maturity_rating
from cnt
