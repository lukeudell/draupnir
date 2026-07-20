# Draupnir: case study source

The long-form narrative for lukeudell.com: what this project measures, how each
metric is defined, and why. Every figure here is reproducible from a cold clone
at seed 42.

This file is the source for `project.yaml`. Edit here, then mirror into the config.

---

## Overview

You are the founding analytics engineer at a new ad-supported streaming service.
There is no warehouse, no metrics layer, and no agreed definition of anything.
Stakeholders arrive with questions rather than requirements: *is our inventory
worth what we think it is? are we annoying viewers? what happens if our biggest
advertiser leaves?*

The work is deciding what to measure, defining it precisely enough to compute, and
building the pipeline that computes it. This project is that pipeline: synthetic
ad-supported streaming telemetry, generated with domain-appropriate distributions,
loaded into Postgres, modelled with dbt across three layers, and read by a
Streamlit campaign pacing monitor.

Everything is self-hosted and open source. No third-party analytics, no managed
warehouse, no vendor account required to run it.

## The dataset: distributions, not noise

About 141,000 viewing sessions producing 500,000 ad requests and 410,000
impressions, across 50,000 subscribers, 100 advertisers, 500 campaigns and 2,000
content items, over 2025-12-01 to 2026-03-01, under seed 42.

Two of those counts are derived rather than chosen. Sessions are the unit of
simulation, and how far a session gets decides both its watch duration and the
ad breaks it passes through, so ad load falls out of viewing instead of being
set independently. The impression count is then the request count times the 0.82
fill rate. Deriving both is what makes the published rates reproducible.

Each column uses a distribution chosen for a reason, because realistic data exposes
real query-planner behaviour and produces metrics with realistic tails. Uniform
random data makes every campaign look average and every plan look alike.

| Element | Distribution | Why |
|---|---|---|
| Bid CPM | Log-normal about a per-vertical mean, σ=0.3 | Ad pricing is set by what the category can bear: $18 QSR to $40 Finance. Log-normal because bids cluster low with a long premium tail |
| Clearing revenue | Bid × Uniform(0.7, 1.0) | Second-price auctions clear below the winning bid |
| Request timing | Gaussian diurnal, peak 20:30, σ=3h, weekends ×1.2 | Streaming is prime-time behaviour, and weekends shift volume up |
| Subscriber activity | Pareto α=1.5 | A minority of heavy viewers generate most requests |
| Content popularity | Pareto α=1.8 | A minority of titles carry most viewing |
| Completion | `Beta(r·10, (1−r)·10) > 0.5` per slot | Per-slot base rate `r` decaying from 0.92 pre-roll to 0.55 post-roll |
| Viewability | Beta, conditioned on device and slot | Smart TV `Beta(15,1)`, mobile/tablet `Beta(5,2)` discounted 15%, else Bernoulli on the slot rate |
| Fill | Bernoulli p=0.82 | 18% of requests find no buyer. Every filled request yields exactly one impression, so this rate alone sets the impression count |
| Campaign volume per advertiser | Weighted by spend tier | Enterprise 4.0 : Growth 2.0 : Starter 1.0 : Self-Serve 0.5 |

The slot decay is the structural fact the whole model rests on: inventory is not
fungible. A pre-roll impression completes 92% of the time and is viewable 95% of the
time; a post-roll impression completes 55% and is viewable 60%. Two impressions,
the same nominal product, materially different value.

| Slot | Duration | Completion | Viewability |
|---|---|---|---|
| `pre_roll_1` | 15s | 0.92 | 0.95 |
| `pre_roll_2` | 30s | 0.88 | 0.93 |
| `mid_roll_1` | 15s | 0.80 | 0.88 |
| `mid_roll_2` | 30s | 0.75 | 0.85 |
| `mid_roll_3` | 15s | 0.70 | 0.82 |
| `post_roll_1` | 15s | 0.55 | 0.60 |

## The pipeline

Four stages: generate, load, transform, analyse.

**Generate.** `data/generate_ads_data.py` writes nine CSVs: ad slots, advertisers,
content catalogue, subscribers, campaigns, a date dimension, viewing sessions, ad
requests and ad impressions. Sessions are generated first and the requests are
emitted from them. Only ads-tier subscribers view; the 20% on `premium_no_ads`
are excluded at source, which is what makes the subscriber count and the reach
count differ, and what keeps them out of the RPSH denominator where they would
dilute a rate they generate no revenue for.

**Load.** `data/load_ads_data.py` creates the `ads_staging` schema and bulk-loads
each CSV with `COPY ... FROM STDIN`.

**Transform.** 23 dbt models across three layers:

| Layer | Schema | Materialisation | Models |
|---|---|---|---|
| Staging | `ads_staging_v` | view | 8: `stg_advertisers`, `stg_ad_impressions`, `stg_ad_requests`, `stg_ad_slots`, `stg_campaigns`, `stg_content_catalog`, `stg_subscribers`, `stg_viewing_sessions` |
| Marts | `ads_mart` | table | 9: `dim_advertisers`, `dim_ad_slots`, `dim_campaigns`, `dim_content`, `dim_date_ads`, `dim_subscribers`, `fct_ad_impressions`, `fct_campaign_daily`, `fct_viewing_sessions` |
| Analytics | `ads_analytics` | table | 6: `mart_platform_health`, `mart_campaign_performance`, `mart_frequency_analysis`, `mart_advertiser_summary`, `mart_content_monetization`, `mart_advertiser_concentration` |

The marts carry enforced dbt contracts: 82 columns with their data types declared
and checked at build, read from the live `information_schema` rather than guessed.
A model that changes shape fails the build instead of quietly changing meaning.

Surrogate keys come from `dbt_utils.generate_surrogate_key()`. `fct_ad_impressions`
is the grain of the whole model, one row per impression, and joins six dimensions
including a date join derived from the impression timestamp. `fct_campaign_daily`
aggregates it to campaign × day.

There is no creatives entity. An earlier version of the published diagram showed
one, along with `fct_campaign_pacing` and `mart_revenue_mix`; none of those models
exist. The real names are above.

**Analyse.** The Streamlit "Campaign Pacing Monitor" reads the analytics layer
directly over a read-only role and presents four tabs: platform health, campaign
pacing, frequency and reach, and advertiser mix.

## The metrics

Eight metrics, each chosen because a stakeholder asks the question it answers.

### The eight

**Fill rate**: `impressions / ad_requests`. Are we monetising the inventory we
have? Every unfilled slot is revenue that cannot be recovered later; ad inventory is
the most perishable asset in media. Below 70% points at a demand gap; 80–90% is
healthy; above 95% means supply is constrained and floor prices are too low.
Computed daily in `mart_platform_health`, which is the only model joining
`stg_ad_requests`; without that denominator there is no fill rate at all.

**eCPM**: `(revenue / impressions) × 1000`. What is our inventory worth? eCPM is
the common currency that makes CPM, CPC and CPA deals comparable. Below $8 suggests
poor demand quality; $12–25 is the healthy streaming range; above $30 signals
premium inventory.

**Completion rate**: `completed / started`. Are viewers watching? This drives
advertiser satisfaction and renewal directly, and low completion means ad fatigue,
poor targeting or excessive ad load. Benchmarks track slot position: ~92% pre-roll,
~85% mid-roll, ~55% post-roll.

**Viewability**: `viewable / total`, against the IAB standard of 50% of the ad's
pixels visible for 2 continuous seconds. Can advertisers trust the inventory? This
is the baseline credibility metric; as viewable-only billing spreads, low
viewability collapses effective yield regardless of volume. Below 60% is under the
industry standard, ~70% is the benchmark, above 80% is premium.

**Frequency cap compliance**: `subscribers_exceeding_cap / total_reached`. Are we
annoying people? `mart_frequency_analysis` counts impressions per
(subscriber, campaign) pair, compares against the campaign's configured cap, and
aggregates violation rates to campaign level. Under 2% is target; 2–5% warrants
checking the ad server configuration; over 5% is an active ad-fatigue risk.

**Advertiser concentration (HHI)**: `Σ(market_share²)` over percent shares, the
Herfindahl-Hirschman index, the same measure the DOJ applies to merger review.
Revenue diversification is survival: if one advertiser is 40% of revenue, losing
that account is existential. Below 1500 is diversified, 1500–2500 moderate, above
2500 concentrated. `mart_advertiser_summary` produces `revenue_share_pct` per
advertiser; the squaring and summing currently happens in the Streamlit app rather
than in SQL, which means the number is not testable by dbt. Moving it into the
analytics layer is the obvious next change.

### Defined but not yet built

**Revenue per subscriber hour (RPSH)**: `ad_revenue / viewing_hours`. The number
that sits on the boundary between the two constituencies, since it rises both
when inventory is sold well and when viewers are shown more advertising than
they will tolerate. It is the only metric here that is bad in both directions.

Building it was the hardest item in the catalog, and not for plumbing reasons.
The impression grain carries `view_duration_sec`, which is how long an *ad* was
watched; dividing revenue by that gives a completion-weighted eCPM wearing
another name. RPSH needs content viewing time, which nothing in the original
data produced. So viewing sessions became the unit of simulation: a session is
one subscriber's sitting with one title, and how far it gets decides both the
watch duration and the ad breaks it passes through, from one draw. Ad load is
then a consequence of viewing rather than a separate knob.

That inversion also corrected the published thresholds, which is the more
interesting half. RPSH is ad load per hour times eCPM over 1000. The catalog
published $2 / $4 / $6 per hour; at a $25 eCPM the $4 target needs 160
impressions inside a single viewing hour, an ad every 22 seconds. No
ad-supported service reaches it, and none should. The thresholds are now derived
from the arithmetic: 6 ads/hour is $0.15, 14 ads/hour is $0.35. The warehouse
observes $0.238 at 8.5 ads per viewing hour, comfortably inside the healthy
band. A metric worth calling THE metric is worth thresholds that a real platform
could actually hit.

**Campaign pacing ratio.** The intended definition is
`cumulative_spend / (elapsed_days / total_days × budget)`: spend to date against the
share of the flight elapsed, with 0.9–1.1 on pace. It answers whether the advertiser
will get what they paid for, and both under- and over-delivery erode trust.

`fct_campaign_daily` used to ship a different calculation:
`revenue_usd / avg_daily_spend`, comparing a single day's revenue against that
campaign's own average day, with an on-pace band of 0.7–1.3. That detects unusual
days; it does not detect under-delivery against contract, and because the baseline
moves with the spend it never can. Every input the published formula needs was
already computed in the model's own CTE and then discarded.

It now computes the published definition, with flight progress capped at 1.0 so
that a finished flight is measured against the whole budget and no more. Elapsed
time counts calendar days from `flight_start`, not days on which something was
delivered: counting delivery days under-counts elapsed time for a campaign with
gaps, which biases the ratio upward and hides exactly the under-delivery the
metric exists to surface. A null ratio reports `UNKNOWN` rather than `ON_PACE`,
because a missing baseline is not evidence of health.

The interesting part is what changing the metric exposed. A ratio that finally
referenced flight dates and budgets made two upstream bugs visible immediately,
both invisible to the old formula because it used neither:

- Campaigns were assigned to impressions by budget weight with no reference to
  the date, so 43% of campaign-days carried impressions from before the campaign
  had started and 38% from after it ended. Assignment is now restricted to
  campaigns in flight that day, still budget-weighted within the day.
- Campaign budgets came from a guess at daily volume with no connection to the
  impressions the simulation produces. Against real delivery, 96.6% of
  campaign-days read UNDER_PACING: not a pacing signal, a miscalibrated world.
  Budgets are now derived from actual delivery against a target ratio drawn per
  campaign, which makes the spread of outcomes a controlled property. It lands
  at 43.7% under, 26.9% on pace, 29.4% over.

Three reconciliation tests hold the definition in place: the ratio must match the
published formula recomputed from the model's own columns, elapsed days must
equal calendar days since flight start, and the status label must follow from the
rounded ratio it describes.

## Metric interactions

Listing metrics is the easy half. Reading them against each other is the analytics
engineering:

| Pattern | Diagnosis |
|---|---|
| High fill rate + low eCPM | Selling cheap. Floor prices are too low or demand quality is poor; revenue is being left on the table at full inventory utilisation |
| Low completion + high frequency | Ad fatigue. Viewers are seeing too many ads they do not want to finish; churn risk is elevated before any revenue metric moves |
| High RPSH + declining viewability | Short-term revenue extracted at the cost of ad quality. Advertisers will demand make-goods or leave |
| High HHI + over-pacing top campaigns | Concentrated revenue burning too fast. When those budgets exhaust, fill rate and revenue cliff together, and there is no diversified base to absorb it |

Each of these is a leading indicator that no single metric produces. The last one is
the reason pacing and concentration belong on the same dashboard: neither is
alarming alone.

## Engineering discipline

42 declarative dbt tests across three `schema.yml` files: uniqueness on every
surrogate key, not-null on every join column, accepted values on the categorical
dimensions, and referential integrity from fact to dimension. Distribution is
uneven: 20 staging, 20 marts, 2 analytics, and closing the analytics gap is the
known next step.

A read-only `portfolio_reader` role serves the presentation layer. Postgres binds to
loopback by default. No credentials are hardcoded: the app refuses to start without
`PORTFOLIO_DB_PASSWORD` in the environment, and `dbt/profiles.yml` is gitignored.
The Streamlit theme resolves its palette from URL query parameters and validates
every value against a strict `#RRGGBB` allowlist before any of it reaches
`unsafe_allow_html`; that path is the one part of the codebase with a dedicated
test suite.

Known limitations are documented rather than hidden; they are called out inline above.

## What would come next

**Attribution modelling.** Multi-touch attribution connecting ad exposure to
subscriber conversion. Last-touch is table stakes; data-driven attribution is the
goal.

**Incrementality testing.** Holdout experiments measuring true ad lift against
organic behaviour. Without incrementality you are measuring correlation and calling
it causation.

**LTV-weighted bid optimisation.** Weighting auction bids by predicted subscriber
lifetime value. A high-LTV viewer seeing a well-targeted ad is worth more than raw
impression volume.

At production scale the same patterns map to different tools: impression events to
Kafka topics per event type, batch aggregation to Spark, orchestration to Airflow
with SLA monitoring, ad-hoc analysis to Trino, real-time pacing to Flink stateful
processing per campaign, and viewability to a client-side SDK reconciled server
side. dbt Core on Postgres is the right choice at demonstration scale and the wrong
one at a billion impressions a day; knowing which is which is part of the point.
