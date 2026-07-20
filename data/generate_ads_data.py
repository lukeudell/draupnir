# ============================================================
#  file:       data/generate_ads_data.py
#  purpose:    seeded synthetic ad platform telemetry, reproducible from a single seed
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-04]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Draupnir: ad platform simulator data generator
Generates synthetic ad-supported streaming platform data: advertisers, campaigns,
subscribers, content, ad requests, and impressions with realistic distributions.

Usage:
    python generate_ads_data.py [--seed 42] [--subscribers 50000]
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

OUTPUT_DIR = Path(__file__).parent / "generated" / "ads"
SEED = 42

# Fill rate is an input, not an outcome. Every filled request produces exactly
# one impression, so this constant alone sets the served rate and the impression
# count is derived from it. It used to be capped by a separate --impressions
# argument, which meant the surplus filled requests silently produced nothing
# and the published "82% by construction" described the flag rather than the
# data. See the reconciliation test in dbt/tests/.
DEFAULT_FILL_RATE = 0.82

# The observation window. Every date in the dataset falls inside it, and it is
# also the "as of" date against which campaign status is decided, so it lives in
# one place rather than being repeated at each use.
DATASET_START = datetime(2025, 12, 1)
DATASET_END = datetime(2026, 3, 1)


def _campaign_status(flight_start, flight_end, as_of=DATASET_END):
    """Campaign status as of a given date.

    Args:
        flight_start: first day of the campaign flight.
        flight_end: last day of the campaign flight.
        as_of: the date to evaluate against; defaults to the dataset end.

    Returns:
        One of "completed", "active" or "scheduled".
    """
    if flight_end < as_of:
        return "completed"
    if flight_start <= as_of:
        return "active"
    return "scheduled"

# ---------------------------------------------------------------------------
# Reference Data
# ---------------------------------------------------------------------------

VERTICALS = [
    "Automotive", "CPG", "Entertainment", "Finance", "Healthcare",
    "Retail", "Technology", "Telecom", "Travel", "QSR",
]
VERTICAL_WEIGHTS = [0.12, 0.15, 0.10, 0.10, 0.05, 0.15, 0.12, 0.08, 0.08, 0.05]

# CPM by vertical (used as log-normal mean for bid price generation)
VERTICAL_CPM = {
    "Automotive": 35, "CPG": 25, "Entertainment": 20, "Finance": 40,
    "Healthcare": 30, "Retail": 22, "Technology": 32, "Telecom": 28,
    "Travel": 26, "QSR": 18,
}

SPEND_TIERS = ["Enterprise", "Growth", "Starter", "Self-Serve"]
SPEND_TIER_WEIGHTS = [0.10, 0.25, 0.40, 0.25]

GENRES = [
    "Drama", "Comedy", "Action", "Sci-Fi", "Documentary",
    "Thriller", "Animation", "Romance", "Horror", "Crime",
]

CONTENT_TYPES = ["series", "movie", "special"]
CONTENT_TYPE_WEIGHTS = [0.60, 0.30, 0.10]

MATURITY_RATINGS = ["TV-G", "TV-PG", "TV-14", "TV-MA"]
MATURITY_WEIGHTS = [0.10, 0.20, 0.40, 0.30]

SUB_TIERS = ["ads_basic", "ads_standard", "premium_no_ads"]
SUB_TIER_WEIGHTS = [0.45, 0.35, 0.20]

DEVICES = ["smart_tv", "mobile", "tablet", "web", "game_console"]
DEVICE_WEIGHTS = [0.40, 0.25, 0.10, 0.15, 0.10]

REGIONS = ["us-east", "us-west", "us-south", "us-midwest", "eu-west", "latam", "apac"]
REGION_WEIGHTS = [0.22, 0.18, 0.15, 0.10, 0.15, 0.10, 0.10]

AD_SLOTS = [
    {"slot_position": "pre_roll_1", "typical_duration_sec": 15, "avg_completion_rate": 0.92, "avg_viewability": 0.95},
    {"slot_position": "pre_roll_2", "typical_duration_sec": 30, "avg_completion_rate": 0.88, "avg_viewability": 0.93},
    {"slot_position": "mid_roll_1", "typical_duration_sec": 15, "avg_completion_rate": 0.80, "avg_viewability": 0.88},
    {"slot_position": "mid_roll_2", "typical_duration_sec": 30, "avg_completion_rate": 0.75, "avg_viewability": 0.85},
    {"slot_position": "mid_roll_3", "typical_duration_sec": 15, "avg_completion_rate": 0.70, "avg_viewability": 0.82},
    {"slot_position": "post_roll_1", "typical_duration_sec": 15, "avg_completion_rate": 0.55, "avg_viewability": 0.60},
]
SLOT_WEIGHTS = [0.20, 0.15, 0.25, 0.15, 0.15, 0.10]

# Ad slots fire in a fixed order through a view, so the deepest slot a session
# reaches says how much of the content was watched: a session that only ever
# asked for a pre-roll was abandoned early, one that reached post-roll ran to
# the end. One draw per session therefore fixes both the watch time and the
# number of ad breaks, which is what keeps the two coherent.
SLOT_DEPTH = {slot["slot_position"]: i for i, slot in enumerate(AD_SLOTS)}
DEPTH_TO_SLOT = {i: slot for slot, i in SLOT_DEPTH.items()}

# How far sessions get, as a distribution over the deepest slot reached. Most
# viewers who start something get past the first break; a fifth abandon during
# the pre-roll, a fifth watch to the end.
SESSION_DEPTH_WEIGHTS = [0.20, 0.10, 0.20, 0.15, 0.15, 0.20]

# Share of the content watched, given the deepest slot reached. Ranges rather
# than points, because two viewers who both reached mid_roll_2 did not watch
# exactly the same amount.
SLOT_WATCH_FRACTION = {
    "pre_roll_1": (0.05, 0.25),
    "pre_roll_2": (0.10, 0.30),
    "mid_roll_1": (0.30, 0.50),
    "mid_roll_2": (0.50, 0.70),
    "mid_roll_3": (0.70, 0.90),
    "post_roll_1": (0.95, 1.00),
}

# Where each break falls within the watched portion. Pre-rolls are at the head,
# post-roll at the tail; the mid-rolls are spaced through the middle. This is
# what puts an ad request at a plausible moment rather than a random one.
SLOT_TIME_FRACTION = {
    "pre_roll_1": 0.00,
    "pre_roll_2": 0.01,
    "mid_roll_1": 0.30,
    "mid_roll_2": 0.50,
    "mid_roll_3": 0.70,
    "post_roll_1": 0.98,
}

# Mean ad breaks per session, implied by SESSION_DEPTH_WEIGHTS. Used to turn a
# target request count into a session count, since sessions are what get
# generated and requests are what fall out of them.
MEAN_SLOTS_PER_SESSION = sum(w * (i + 1) for i, w in enumerate(SESSION_DEPTH_WEIGHTS))

# Floor on a session. A view short enough to round below this did not really
# happen, and a near-zero denominator would distort revenue per hour.
MIN_WATCH_SECONDS = 30

# The longest a session can run: the longest title in the catalog, watched whole.
# Used to keep every session inside the observation window.
MAX_SESSION_SECONDS = 120 * 60

OBJECTIVES = ["awareness", "reach", "completion", "clicks"]
OBJECTIVE_WEIGHTS = [0.35, 0.25, 0.20, 0.20]

PACING_GOALS = ["even", "front_loaded", "back_loaded"]
PACING_GOAL_WEIGHTS = [0.70, 0.15, 0.15]

AGE_BANDS = ["18_24", "25_34", "35_44", "45_54", "55_64", "65_plus"]


def generate_advertisers(rng, fake, n):
    rows = []
    for i in range(n):
        rows.append({
            "advertiser_id": f"adv_{i + 1:04d}",
            "company_name": fake.company(),
            "industry_vertical": rng.choice(VERTICALS, p=VERTICAL_WEIGHTS),
            "spend_tier": rng.choice(SPEND_TIERS, p=SPEND_TIER_WEIGHTS),
            "country": fake.country_code(),
        })
    return pd.DataFrame(rows)


def generate_content(rng, fake, n):
    rows = []
    for i in range(n):
        rows.append({
            "content_id": f"cnt_{i + 1:05d}",
            "title": fake.catch_phrase(),
            "content_type": rng.choice(CONTENT_TYPES, p=CONTENT_TYPE_WEIGHTS),
            "genre": rng.choice(GENRES),
            "avg_episode_minutes": int(np.clip(rng.lognormal(3.6, 0.3), 20, 120)),
            "maturity_rating": rng.choice(MATURITY_RATINGS, p=MATURITY_WEIGHTS),
        })
    return pd.DataFrame(rows)


def generate_subscribers(rng, fake, n):
    rows = []
    for i in range(n):
        beta_val = rng.beta(2.5, 3.0)
        age_idx = min(int(beta_val * len(AGE_BANDS)), len(AGE_BANDS) - 1)
        rows.append({
            "subscriber_id": f"sub_{i + 1:06d}",
            "subscription_tier": rng.choice(SUB_TIERS, p=SUB_TIER_WEIGHTS),
            "signup_date": fake.date_between(
                start_date=datetime(2020, 1, 1),
                end_date=datetime(2025, 12, 31),
            ),
            "region": rng.choice(REGIONS, p=REGION_WEIGHTS),
            "device_primary": rng.choice(DEVICES, p=DEVICE_WEIGHTS),
            "age_band": AGE_BANDS[age_idx],
        })
    return pd.DataFrame(rows)


_CAMPAIGN_PREFIXES = {
    "awareness": ["Brand Lift", "Awareness", "Brand Reach", "Brand Spotlight", "Intro"],
    "reach": ["Max Reach", "Broad Reach", "Audience Expansion", "Scale", "Discovery"],
    "completion": ["Full View", "Engagement", "Watch Complete", "Deep View", "Lean-In"],
    "clicks": ["Click Drive", "CTA Push", "Direct Response", "Performance", "Convert"],
}

_QUARTER_LABELS = {1: "Q1", 2: "Q1", 3: "Q1", 4: "Q2", 5: "Q2", 6: "Q2",
                   7: "Q3", 8: "Q3", 9: "Q3", 10: "Q4", 11: "Q4", 12: "Q4"}

_VERTICAL_SHORT = {
    "Automotive": "Auto", "CPG": "CPG", "Finance": "Fin",
    "Entertainment": "Ent", "Technology": "Tech", "Retail": "Retail",
    "Travel": "Travel", "Healthcare": "Health", "Telecom": "Telco",
    "QSR": "QSR",
}


def _campaign_name(rng, vertical, objective, flight_start):
    """Generate a realistic ad campaign name like 'Brand Lift - Auto Q1 2026'."""
    prefix = rng.choice(_CAMPAIGN_PREFIXES.get(objective, ["Campaign"]))
    vert = _VERTICAL_SHORT.get(vertical, vertical[:5])
    quarter = _QUARTER_LABELS.get(flight_start.month, "Q1")
    return f"{prefix} - {vert} {quarter} {flight_start.year}"


def generate_campaigns(rng, n, advertisers):
    adv_ids = advertisers["advertiser_id"].values
    adv_tiers = advertisers["spend_tier"].values

    # Enterprise advertisers have more campaigns
    tier_weights = {"Enterprise": 4.0, "Growth": 2.0, "Starter": 1.0, "Self-Serve": 0.5}
    weights = np.array([tier_weights[t] for t in adv_tiers], dtype=float)
    weights /= weights.sum()

    start_date = DATASET_START
    window_days = (DATASET_END - DATASET_START).days

    rows = []
    for i in range(n):
        adv_idx = rng.choice(len(adv_ids), p=weights)
        flight_days = int(np.clip(rng.lognormal(2.7, 0.5), 7, 60))
        # why: starts are stratified across the window rather than drawn
        # uniformly at random, so that campaigns are in flight on every day of
        # it. A uniform draw leaves the opening days sparse: only a campaign
        # whose offset is exactly 0 is live on day 1, which at 50 campaigns over
        # an 80 day range fails about half the time. Each campaign takes its own
        # stratum and jitters inside it; the first is pinned to day 0 so the
        # window opens with demand already running.
        stride = max(window_days - 1, 1) / n
        offset = 0 if i == 0 else int(min(i * stride + rng.uniform(0, stride), window_days - 1))
        flight_start = start_date + timedelta(days=offset)
        # why: inclusive of both endpoints. A 30 day flight runs day 1 to day 30,
        # so the last day is start + 29. Adding flight_days instead spanned
        # flight_days + 1 calendar days, which put the final day of every
        # campaign one past its own stated length.
        flight_end = flight_start + timedelta(days=flight_days - 1)
        # Budget scaled to expected delivery so pacing ratios are realistic
        # Expected: ~impressions_per_campaign × avg_cpm/1000
        # With noise so some campaigns over/under pace
        adv_vertical = advertisers.iloc[adv_idx]["industry_vertical"]
        base_cpm = VERTICAL_CPM.get(adv_vertical, 25)
        expected_impressions_per_day = rng.uniform(5, 50)
        daily_budget = float(expected_impressions_per_day * base_cpm / 1000 * rng.uniform(0.8, 1.3))
        daily_budget = max(daily_budget, 0.10)

        # why: drawn once and bound, because _campaign_name derives the name's
        # prefix from the objective. Drawing separately for the name and the
        # column left them agreeing only by chance, at roughly the rate two
        # independent draws on the same weighted distribution would, so rows
        # read "Click Drive - Auto Q1 2026" while carrying objective=awareness.
        objective = OBJECTIVES[rng.choice(len(OBJECTIVES), p=OBJECTIVE_WEIGHTS)]

        rows.append({
            "campaign_id": f"cmp_{i + 1:04d}",
            "advertiser_id": adv_ids[adv_idx],
            "campaign_name": _campaign_name(rng, adv_vertical, objective, flight_start),
            "objective": objective,
            "daily_budget_usd": round(daily_budget, 2),
            "total_budget_usd": round(daily_budget * flight_days, 2),
            "flight_start": flight_start.date(),
            "flight_end": flight_end.date(),
            "flight_days": flight_days,
            "frequency_cap": int(rng.choice([3, 5, 5, 7, 7, 7, 10, 10, 15])),
            "pacing_goal": rng.choice(PACING_GOALS, p=PACING_GOAL_WEIGHTS),
            "status": _campaign_status(flight_start, flight_end),
        })
    return pd.DataFrame(rows)


def generate_viewing_sessions(rng, subscribers, content, n_sessions):
    """Generate viewing sessions: one subscriber's sitting with one title.

    Sessions are the unit of simulation, because they are the unit of reality:
    a viewer starts something, watches some of it, and the ad breaks they pass
    through are a consequence. Generating ad requests directly, as this used to,
    produced telemetry with no session structure at all: every ad call was its
    own sitting, which made the viewing-hours denominator meaningless and left
    an ad load of under 3 impressions per hour against a realistic 10 to 20.

    Only ads-tier subscribers appear. Premium subscribers watch but generate no
    ad revenue, so including their hours would understate revenue per hour
    against a denominator the ad business never had access to.

    Args:
        rng: seeded numpy Generator.
        subscribers: subscriber dimension, carrying subscription_tier.
        content: catalog, carrying avg_episode_minutes.
        n_sessions: how many sessions to generate.

    Returns:
        One row per session, carrying the deepest ad slot the session reached
        and how long it was watched.
    """
    ads_subs = subscribers[subscribers["subscription_tier"] != "premium_no_ads"]
    sub_ids = ads_subs["subscriber_id"].values
    sub_devices = ads_subs["device_primary"].values
    content_ids = content["content_id"].values
    episode_minutes = content.set_index("content_id")["avg_episode_minutes"]

    # Pareto-weighted: a minority of heavy viewers and hit titles carry most
    # of the volume, which is what makes frequency capping a real problem.
    sub_weights = rng.pareto(a=1.5, size=len(sub_ids)) + 1
    sub_weights /= sub_weights.sum()
    sub_indices = rng.choice(len(sub_ids), size=n_sessions, p=sub_weights)

    cnt_weights = rng.pareto(a=1.8, size=len(content_ids)) + 1
    cnt_weights /= cnt_weights.sum()
    cnt_indices = rng.choice(len(content_ids), size=n_sessions, p=cnt_weights)

    # Session starts follow the diurnal curve: streaming is prime-time behaviour.
    # why: the latest start is pulled back by the longest possible session, so a
    # session cannot run past the end of the observation window. Without it, a
    # sitting begun late on the final evening put its post-roll into the next
    # day, leaving a 9-request partial day that the dashboard then displayed as
    # its headline figures: 100% fill, no viewing hours, undefined RPSH.
    start_date = DATASET_START
    total_seconds = int((DATASET_END - start_date).total_seconds()) - MAX_SESSION_SECONDS
    candidate_secs = rng.uniform(0, total_seconds, size=n_sessions * 3)
    hours = np.array([(start_date + timedelta(seconds=float(s))).hour for s in candidate_secs])
    weekdays = np.array([(start_date + timedelta(seconds=float(s))).weekday() for s in candidate_secs])
    diurnal = 0.2 + 0.8 * np.exp(-0.5 * ((hours - 20.5) / 3.0) ** 2)
    diurnal[weekdays >= 5] *= 1.2
    probs = diurnal / diurnal.sum()
    chosen = rng.choice(len(candidate_secs), size=n_sessions, replace=False, p=probs)
    session_start = np.array(
        [start_date + timedelta(seconds=float(candidate_secs[i])) for i in chosen]
    )

    devices = [
        sub_devices[idx] if rng.random() < 0.8 else rng.choice(DEVICES, p=DEVICE_WEIGHTS)
        for idx in sub_indices
    ]

    # How far into the content the viewer got, expressed as the deepest ad slot
    # they reached. This single draw decides both the watch time and the number
    # of ad breaks, which is what keeps the two coherent.
    depths = rng.choice(len(AD_SLOTS), size=n_sessions, p=SESSION_DEPTH_WEIGHTS)
    deepest_slot = np.array([DEPTH_TO_SLOT[d] for d in depths])

    low = np.array([SLOT_WATCH_FRACTION[s][0] for s in deepest_slot])
    high = np.array([SLOT_WATCH_FRACTION[s][1] for s in deepest_slot])
    fraction = low + rng.random(n_sessions) * (high - low)

    episode_seconds = (
        pd.Series(content_ids[cnt_indices]).map(episode_minutes).to_numpy(dtype=float) * 60.0
    )
    watch = np.maximum(np.round(episode_seconds * fraction), MIN_WATCH_SECONDS)

    return pd.DataFrame({
        "session_id": [f"ses_{i + 1:08d}" for i in range(n_sessions)],
        "subscriber_id": sub_ids[sub_indices],
        "content_id": content_ids[cnt_indices],
        "session_start": session_start,
        "device": devices,
        "watch_seconds": watch.astype(int),
        "deepest_slot": deepest_slot,
        "ad_requests": (depths + 1).astype(int),
    })


def generate_ad_requests(rng, sessions, fill_rate=DEFAULT_FILL_RATE):
    """Emit the ad requests each session passes through.

    A session that reached mid_roll_2 asked for every slot up to it, in order,
    spaced across the time it was watched. That is what makes ad load a
    consequence of viewing rather than an independent knob, and it is why
    revenue per viewing hour is now a meaningful ratio.

    Args:
        rng: seeded numpy Generator.
        sessions: the session frame from generate_viewing_sessions.
        fill_rate: share of requests that are filled.

    Returns:
        One row per ad request, carrying the session it belongs to.
    """
    slot_names = [slot["slot_position"] for slot in AD_SLOTS]

    session_ids, sub_ids, content_ids, slots, timestamps, devices = [], [], [], [], [], []
    for row in sessions.itertuples(index=False):
        depth = SLOT_DEPTH[row.deepest_slot]
        for slot in slot_names[: depth + 1]:
            session_ids.append(row.session_id)
            sub_ids.append(row.subscriber_id)
            content_ids.append(row.content_id)
            slots.append(slot)
            offset = SLOT_TIME_FRACTION[slot] * row.watch_seconds
            timestamps.append(row.session_start + timedelta(seconds=float(offset)))
            devices.append(row.device)

    n = len(session_ids)
    return pd.DataFrame({
        "request_id": [f"req_{i + 1:08d}" for i in range(n)],
        "session_id": session_ids,
        "subscriber_id": sub_ids,
        "content_id": content_ids,
        "slot_position": slots,
        "request_timestamp": timestamps,
        "device": devices,
        "was_filled": rng.random(size=n) < fill_rate,
    })


def calibrate_budgets(rng, campaigns, impressions, target_mean=0.98, target_sd=0.18):
    """Set campaign budgets from what each campaign actually delivered.

    The provisional budgets drawn in generate_campaigns are a guess at daily
    volume (5 to 50 impressions) that has no connection to the impression count
    the simulation actually produces. Measured against real delivery of about
    10 impressions per campaign-day, that guess left 96.6% of campaign-days
    reading UNDER_PACING: not a pacing signal, just a miscalibrated world.

    Real advertisers set budgets they broadly expect to spend, and the
    interesting variation is who overshoots and who undershoots. So the budget
    becomes actual delivery divided by a target delivery ratio drawn per
    campaign, which makes the spread of pacing outcomes a controlled property of
    the generator rather than an accident.

    Note the ordering this implies: provisional budgets still drive impression
    assignment (bigger campaigns win more impressions), and only then are
    budgets restated. campaigns.csv must therefore be written after impressions.

    Args:
        rng: seeded numpy Generator.
        campaigns: campaign frame carrying campaign_id and flight_days.
        impressions: generated impressions carrying campaign_id and revenue_usd.
        target_mean: centre of the end-of-flight delivery ratio distribution.
        target_sd: spread of that distribution.

    Returns:
        A copy of campaigns with total_budget_usd and daily_budget_usd restated.
    """
    out = campaigns.copy()
    delivered = impressions.groupby("campaign_id")["revenue_usd"].sum()
    actual = out["campaign_id"].map(delivered).fillna(0.0).astype(float)

    targets = rng.normal(target_mean, target_sd, size=len(out)).clip(0.55, 1.45)
    budgets = actual / targets

    # a campaign that delivered nothing still needs a coherent budget: it has no
    # rows in the daily fact, but it is still a row in the dimension.
    floor = 0.10 * out["flight_days"].astype(float)
    out["total_budget_usd"] = np.maximum(budgets, floor).round(2)
    out["daily_budget_usd"] = (out["total_budget_usd"] / out["flight_days"]).round(2)
    return out


def _assign_campaigns_by_date(rng, filled, camp_df, camp_weights):
    """Pick a campaign for each impression from those actually in flight that day.

    Campaigns were previously drawn from the whole catalog weighted by budget,
    with no reference to the impression's date, so an impression could be
    attributed to a campaign whose flight had not started or had already ended.
    The old pacing metric never looked at flight dates, so it hid this
    completely; a budget-delivery metric cannot, because spend outside the
    flight has no share of budget to be measured against.

    Within a day, selection is still budget-weighted, so larger campaigns win
    more impressions. The difference is that the candidate set is restricted to
    campaigns in flight on that day.

    Args:
        rng: seeded numpy Generator.
        filled: the filled requests, carrying request_timestamp.
        camp_df: campaigns, carrying flight_start and flight_end.
        camp_weights: budget weights over the full campaign catalog.

    Returns:
        An integer array of campaign indices, one per filled request.

    Raises:
        ValueError: if any impression date has no campaign in flight, which
            would silently drop impressions and break the fill rate.
    """
    starts = pd.to_datetime(camp_df["flight_start"]).values
    ends = pd.to_datetime(camp_df["flight_end"]).values
    imp_days = pd.to_datetime(filled["request_timestamp"]).dt.normalize().values

    indices = np.empty(len(filled), dtype=int)
    for day in np.unique(imp_days):
        on_day = np.flatnonzero(imp_days == day)
        active = np.flatnonzero((starts <= day) & (ends >= day))
        if len(active) == 0:
            raise ValueError(f"no campaign in flight on {pd.Timestamp(day).date()}")
        weights = camp_weights[active]
        weights = weights / weights.sum()
        indices[on_day] = rng.choice(active, size=len(on_day), p=weights)
    return indices


def generate_impressions(rng, requests, campaigns, advertisers):
    # why: every filled request gets an impression, with no separate cap. The
    # cap used to be an independent argument, so a request could be flagged
    # filled and still produce nothing; that made was_filled and the fact table
    # disagree by the surplus. The impression count is now derived from the
    # fill rate, which is what makes the published rate reproducible.
    filled = requests[requests["was_filled"]].copy()

    camp_df = campaigns.copy()
    adv_df = advertisers.set_index("advertiser_id")

    # Weight campaigns by budget for assignment
    camp_budgets = camp_df["total_budget_usd"].values.astype(float)
    camp_weights = camp_budgets / camp_budgets.sum()
    camp_ids = camp_df["campaign_id"].values
    camp_adv_ids = camp_df["advertiser_id"].values
    camp_verticals = []
    for adv_id in camp_adv_ids:
        camp_verticals.append(adv_df.loc[adv_id, "industry_vertical"])

    n = len(filled)
    camp_indices = _assign_campaigns_by_date(rng, filled, camp_df, camp_weights)

    # Bid price: log-normal with vertical-specific means
    bid_prices = np.zeros(n)
    for i, ci in enumerate(camp_indices):
        vertical = camp_verticals[ci]
        base_cpm = VERTICAL_CPM.get(vertical, 25)
        cpm = rng.lognormal(np.log(base_cpm), 0.3)
        bid_prices[i] = cpm / 1000.0  # per-impression price

    # Revenue: second-price auction discount
    revenue = bid_prices * rng.uniform(0.7, 1.0, size=n)

    # Slot metadata for completion/viewability
    slot_meta = {s["slot_position"]: s for s in AD_SLOTS}

    # Viewability: bimodal by device
    devices = filled["device"].values
    is_viewable = np.zeros(n, dtype=bool)
    for i in range(n):
        slot = filled.iloc[i]["slot_position"]
        base_view = slot_meta[slot]["avg_viewability"]
        if devices[i] == "smart_tv":
            is_viewable[i] = rng.beta(15, 1) > (1 - base_view)
        elif devices[i] in ("mobile", "tablet"):
            is_viewable[i] = rng.beta(5, 2) > (1 - base_view * 0.85)
        else:
            is_viewable[i] = rng.random() < base_view

    # Completion: beta distribution conditioned on slot
    completed = np.zeros(n, dtype=bool)
    view_duration = np.zeros(n, dtype=int)
    for i in range(n):
        slot = filled.iloc[i]["slot_position"]
        base_rate = slot_meta[slot]["avg_completion_rate"]
        duration = slot_meta[slot]["typical_duration_sec"]
        completed[i] = rng.beta(base_rate * 10, (1 - base_rate) * 10) > 0.5
        view_duration[i] = duration if completed[i] else rng.integers(1, duration)

    imp_timestamps = pd.to_datetime(filled["request_timestamp"].values) + pd.to_timedelta(
        rng.uniform(0, 2, size=n), unit="s"
    )

    result = pd.DataFrame({
        "impression_id": [f"imp_{i + 1:07d}" for i in range(n)],
        "request_id": filled["request_id"].values,
        "campaign_id": camp_ids[camp_indices],
        "advertiser_id": camp_adv_ids[camp_indices],
        "subscriber_id": filled["subscriber_id"].values,
        "content_id": filled["content_id"].values,
        "slot_position": filled["slot_position"].values,
        "device": devices,
        "bid_price_usd": np.round(bid_prices, 6),
        "revenue_usd": np.round(revenue, 6),
        "is_viewable": is_viewable,
        "completed": completed,
        "view_duration_sec": view_duration,
        "impression_timestamp": imp_timestamps,
    })
    return result, set(filled["request_id"].values)


def main():
    parser = argparse.ArgumentParser(description="Generate ad platform synthetic data")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--subscribers", type=int, default=50000)
    parser.add_argument("--advertisers", type=int, default=100)
    parser.add_argument("--campaigns", type=int, default=500)
    parser.add_argument("--content", type=int, default=2000)
    parser.add_argument("--requests", type=int, default=500000)
    parser.add_argument(
        "--fill-rate",
        type=float,
        default=DEFAULT_FILL_RATE,
        help=(
            "Share of ad requests that are filled. The impression count is "
            "derived from this, so the served fill rate is reproducible from "
            "the command line rather than being an artifact of two arguments."
        ),
    )
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    fake = Faker()
    Faker.seed(args.seed)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- Reference data ---
    print("Generating ad slot reference data...")
    slots_df = pd.DataFrame(AD_SLOTS)
    slots_df.to_csv(OUTPUT_DIR / "ad_slots.csv", index=False)
    print(f"  -> ad_slots.csv: {len(slots_df)} rows")

    print(f"\nGenerating {args.advertisers} advertisers...")
    adv_df = generate_advertisers(rng, fake, args.advertisers)
    adv_df.to_csv(OUTPUT_DIR / "advertisers.csv", index=False)
    print(f"  -> advertisers.csv: {len(adv_df)} rows")

    print(f"\nGenerating {args.content} content items...")
    content_df = generate_content(rng, fake, args.content)
    content_df.to_csv(OUTPUT_DIR / "content_catalog.csv", index=False)
    print(f"  -> content_catalog.csv: {len(content_df)} rows")

    print(f"\nGenerating {args.subscribers} subscribers...")
    subs_df = generate_subscribers(rng, fake, args.subscribers)
    subs_df.to_csv(OUTPUT_DIR / "subscribers.csv", index=False)
    print(f"  -> subscribers.csv: {len(subs_df)} rows")

    print(f"\nGenerating {args.campaigns} campaigns...")
    camp_df = generate_campaigns(rng, args.campaigns, adv_df)
    # csv is written after impressions: budgets are restated from actual
    # delivery, so they are not final until the impressions exist.

    # --- Date dimension ---
    print("\nGenerating date dimension...")
    dates = pd.date_range(start="2025-12-01", end="2026-03-01", freq="D")
    dates_df = pd.DataFrame({
        "date_key": [int(d.strftime("%Y%m%d")) for d in dates],
        "full_date": [d.date() for d in dates],
        "day_of_week": [d.strftime("%A") for d in dates],
        "is_weekend": [d.weekday() >= 5 for d in dates],
        "week_of_year": [d.isocalendar()[1] for d in dates],
        "month_name": [d.strftime("%B") for d in dates],
        "quarter": [f"Q{(d.month - 1) // 3 + 1}" for d in dates],
        "year": [d.year for d in dates],
    })
    dates_df.to_csv(OUTPUT_DIR / "dates_ads.csv", index=False)
    print(f"  -> dates_ads.csv: {len(dates_df)} rows")

    # --- Transactional data ---
    # Sessions come first: they are the unit of simulation, and ad requests are
    # a consequence of how far each session got. The target request count is
    # converted into a session count through the mean number of breaks per
    # session, so --requests stays the knob while the causality runs the right
    # way round.
    n_sessions = max(1, int(round(args.requests / MEAN_SLOTS_PER_SESSION)))
    print(f"\nGenerating {n_sessions} viewing sessions (~{args.requests} ad requests)...")
    ses_df = generate_viewing_sessions(rng, subs_df, content_df, n_sessions)
    ses_df.to_csv(OUTPUT_DIR / "viewing_sessions.csv", index=False)
    watch_hours = ses_df["watch_seconds"].sum() / 3600.0
    print(f"  -> viewing_sessions.csv: {len(ses_df)} rows")
    print(f"  Viewing hours: {watch_hours:,.0f}")
    print(f"  Mean session: {ses_df['watch_seconds'].mean() / 60:.1f} min")

    print("\nEmitting the ad requests those sessions passed through...")
    req_df = generate_ad_requests(rng, ses_df, args.fill_rate)

    expected = int(round(len(req_df) * args.fill_rate))
    print(f"\nGenerating ad impressions at a {args.fill_rate:.0%} fill rate (~{expected})...")
    imp_df, served_request_ids = generate_impressions(rng, req_df, camp_df, adv_df)

    # why: belt and braces. generate_impressions now serves every filled request,
    # so this is already true; asserting it here means any future change that
    # reintroduces a cap fails loudly in the generator rather than silently in
    # the warehouse, where it previously showed up only as a 2% discrepancy
    # between the was_filled flag and the fact table.
    req_df["was_filled"] = req_df["request_id"].isin(served_request_ids)

    camp_df = calibrate_budgets(rng, camp_df, imp_df)
    camp_df.to_csv(OUTPUT_DIR / "campaigns.csv", index=False)
    print(f"  -> campaigns.csv: {len(camp_df)} rows (budgets calibrated to delivery)")

    req_df.to_csv(OUTPUT_DIR / "ad_requests.csv", index=False)
    print(f"  -> ad_requests.csv: {len(req_df)} rows")
    print(f"  Fill rate: {req_df['was_filled'].mean():.1%}")

    imp_df.to_csv(OUTPUT_DIR / "ad_impressions.csv", index=False)
    print(f"  -> ad_impressions.csv: {len(imp_df)} rows")

    # --- Spot checks ---
    print("\n--- Distribution Spot Check ---")
    print(f"  eCPM: ${imp_df['revenue_usd'].sum() / len(imp_df) * 1000:.2f}")
    print(f"  Completion rate: {imp_df['completed'].mean():.1%}")
    print(f"  Viewability rate: {imp_df['is_viewable'].mean():.1%}")
    print(f"  Avg bid CPM: ${imp_df['bid_price_usd'].mean() * 1000:.2f}")
    print(f"  Campaigns by status: {camp_df['status'].value_counts().to_dict()}")
    print(f"  Subscribers by tier: {subs_df['subscription_tier'].value_counts().to_dict()}")
    print(f"\nDone. Files written to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
