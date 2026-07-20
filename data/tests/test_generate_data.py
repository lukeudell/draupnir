# ============================================================
#  file:       data/tests/test_generate_data.py
#  purpose:    property tests pinning the generator's documented distributions
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-02] [STD-14]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Property tests for the synthetic data generator.

These assert the invariants the published narrative depends on, because a
generator that quietly drifts makes every downstream number wrong while the
pipeline stays green. Loads the sibling module by explicit path so the suite
does not depend on sys.path or the pytest rootdir.
"""

import importlib.util
import pathlib
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

_MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent / "generate_ads_data.py"
_spec = importlib.util.spec_from_file_location("generate_ads_data", _MODULE_PATH)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def _requests_for(rng, subscribers, content, n_requests, fill_rate=0.82):
    """Generate roughly n_requests ad requests via the sessions that produce them.

    Requests are no longer drawn directly: sessions are the unit of simulation
    and requests fall out of them. This converts a request target into the
    session count that yields it, the same way the generator's own main does.
    """
    n_sessions = max(1, int(round(n_requests / gen.MEAN_SLOTS_PER_SESSION)))
    sessions = gen.generate_viewing_sessions(rng, subscribers, content, n_sessions)
    return gen.generate_ad_requests(rng, sessions, fill_rate)


@pytest.fixture
def rng():
    return np.random.default_rng(gen.SEED)


@pytest.fixture
def subscribers():
    # every subscriber is ads-tier: the premium tier is filtered out upstream
    # and would only add noise to the fill-rate assertions below.
    return pd.DataFrame({
        "subscriber_id": [f"sub_{i:05d}" for i in range(500)],
        "subscription_tier": ["ad_supported"] * 500,
        "device_primary": ["smart_tv"] * 500,
    })


@pytest.fixture
def content():
    # avg_episode_minutes is load-bearing now: session watch time is a fraction
    # of it, so a catalog without it cannot produce sessions at all.
    return pd.DataFrame({
        "content_id": [f"cnt_{i:04d}" for i in range(50)],
        "avg_episode_minutes": [20 + (i % 8) * 10 for i in range(50)],
    })


class TestCampaignStatus:
    """
    Status is decided against the end of the observation window, not against
    wall-clock now, so a rebuild in six months produces the same statuses as
    the first one. That is the property worth pinning.
    """

    def test_flight_entirely_before_the_window_end_is_completed(self):
        assert gen._campaign_status(
            gen.DATASET_START, gen.DATASET_START + timedelta(days=30)
        ) == "completed"

    def test_flight_straddling_the_window_end_is_active(self):
        assert gen._campaign_status(
            gen.DATASET_END - timedelta(days=5), gen.DATASET_END + timedelta(days=5)
        ) == "active"

    def test_flight_entirely_after_the_window_end_is_scheduled(self):
        assert gen._campaign_status(
            gen.DATASET_END + timedelta(days=1), gen.DATASET_END + timedelta(days=10)
        ) == "scheduled"

    def test_flight_ending_exactly_on_the_window_end_is_active(self):
        # boundary: flight_end < as_of is false, flight_start <= as_of is true
        assert gen._campaign_status(gen.DATASET_START, gen.DATASET_END) == "active"

    def test_status_does_not_depend_on_wall_clock(self):
        flight_start = gen.DATASET_START
        flight_end = gen.DATASET_START + timedelta(days=30)
        far_future = gen.DATASET_END + timedelta(days=3650)
        assert gen._campaign_status(flight_start, flight_end) == "completed"
        assert gen._campaign_status(flight_start, flight_end, as_of=far_future) == "completed"


class TestViewingSessions:
    """
    Sessions are the unit of simulation and the denominator of RPSH, so the
    invariant that matters is that watch time and ad breaks come from the same
    draw. Generating them independently is what produced telemetry with an ad
    load of under 3 impressions per viewing hour against a realistic 10 to 20.
    """

    @pytest.fixture
    def sessions(self, rng, subscribers, content):
        return gen.generate_viewing_sessions(rng, subscribers, content, 3000)

    def test_watch_time_respects_the_floor(self, sessions):
        assert (sessions["watch_seconds"] >= gen.MIN_WATCH_SECONDS).all()

    def test_ad_breaks_follow_from_the_depth_reached(self, sessions):
        expected = sessions["deepest_slot"].map(gen.SLOT_DEPTH) + 1
        assert (sessions["ad_requests"] == expected).all()

    def test_deeper_sessions_watch_longer_on_average(self, sessions):
        means = sessions.groupby(
            sessions["deepest_slot"].map(gen.SLOT_DEPTH)
        )["watch_seconds"].mean()
        assert list(means.index) == sorted(means.index)
        assert means.is_monotonic_increasing, "watch time must rise with slot depth"

    def test_only_ad_supported_subscribers_view(self, sessions, subscribers):
        ads_tier = set(
            subscribers.loc[
                subscribers["subscription_tier"] != "premium_no_ads", "subscriber_id"
            ]
        )
        assert set(sessions["subscriber_id"]) <= ads_tier

    def test_sessions_start_inside_the_observation_window(self, sessions):
        starts = pd.to_datetime(sessions["session_start"])
        assert starts.min() >= gen.DATASET_START
        assert starts.max() < gen.DATASET_END

    def test_session_ids_are_unique(self, sessions):
        assert sessions["session_id"].is_unique


class TestRequestsFollowSessions:
    """Ad requests are a consequence of viewing, not an independent draw."""

    @pytest.fixture
    def generated(self, rng, subscribers, content):
        sessions = gen.generate_viewing_sessions(rng, subscribers, content, 2000)
        requests = gen.generate_ad_requests(rng, sessions, 0.82)
        return sessions, requests

    def test_every_request_belongs_to_a_session(self, generated):
        sessions, requests = generated
        assert set(requests["session_id"]) <= set(sessions["session_id"])

    def test_request_count_matches_the_breaks_the_sessions_declared(self, generated):
        sessions, requests = generated
        assert len(requests) == int(sessions["ad_requests"].sum())

    def test_each_session_emits_a_prefix_of_the_slot_order(self, generated):
        sessions, requests = generated
        order = [slot["slot_position"] for slot in gen.AD_SLOTS]
        by_session = requests.groupby("session_id")["slot_position"].apply(list)
        depth_by_session = dict(zip(sessions["session_id"], sessions["deepest_slot"]))
        for session_id, slots in by_session.items():
            depth = gen.SLOT_DEPTH[depth_by_session[session_id]]
            assert slots == order[: depth + 1]

    def test_requests_fall_within_the_session_they_belong_to(self, generated):
        sessions, requests = generated
        merged = requests.merge(
            sessions[["session_id", "session_start", "watch_seconds"]], on="session_id"
        )
        ts = pd.to_datetime(merged["request_timestamp"])
        start = pd.to_datetime(merged["session_start"])
        assert (ts >= start).all()
        assert (ts <= start + pd.to_timedelta(merged["watch_seconds"], unit="s")).all()

    def test_ad_load_is_in_a_plausible_range(self, generated):
        # the defect this guards: independent draws gave 2.9 impressions per
        # viewing hour, where real ad-supported streaming runs about 10 to 20
        sessions, requests = generated
        hours = sessions["watch_seconds"].sum() / 3600.0
        ad_load = len(requests) / hours
        assert 6 <= ad_load <= 25, f"ad load {ad_load:.1f} per hour is not plausible"

    def test_request_ids_are_unique(self, generated):
        _, requests = generated
        assert requests["request_id"].is_unique


class TestCampaignNameMatchesObjective:
    """
    The name's prefix is derived from the objective, so the two must agree on
    every row. They were previously drawn independently from the same weighted
    distribution and agreed only by luck, producing rows like
    "Click Drive - Auto Q1 2026" carrying objective=awareness. Nothing failed,
    because nothing asserted the relationship.
    """

    @pytest.fixture
    def campaigns(self, rng):
        advertisers = pd.DataFrame({
            "advertiser_id": [f"adv_{i:04d}" for i in range(40)],
            "spend_tier": ["Enterprise", "Growth", "Starter", "Self-Serve"] * 10,
            "industry_vertical": ["Retail", "Finance", "Technology", "CPG"] * 10,
        })
        return gen.generate_campaigns(rng, 400, advertisers)

    def test_every_name_prefix_belongs_to_its_objective(self, campaigns):
        for _, row in campaigns.iterrows():
            prefix = row["campaign_name"].split(" - ")[0]
            allowed = gen._CAMPAIGN_PREFIXES[row["objective"]]
            assert prefix in allowed, (
                f"{row['campaign_name']!r} carries objective {row['objective']!r}"
            )

    def test_prefix_sets_are_disjoint_so_the_check_above_has_teeth(self):
        # if two objectives shared a prefix the assertion could pass by accident
        seen = set()
        for prefixes in gen._CAMPAIGN_PREFIXES.values():
            assert not seen & set(prefixes)
            seen |= set(prefixes)

    def test_all_objectives_are_represented(self, campaigns):
        assert set(campaigns["objective"]) == set(gen.OBJECTIVES)


class TestBudgetCalibration:
    """
    Budgets are restated from actual delivery so the spread of pacing outcomes
    is a controlled property rather than an accident. Before this, provisional
    budgets guessed 5 to 50 impressions a day against real delivery of about 10,
    and 96.6% of campaign-days read UNDER_PACING.
    """

    @pytest.fixture
    def campaigns(self):
        return pd.DataFrame({
            "campaign_id": [f"cmp_{i:04d}" for i in range(200)],
            "flight_days": [30] * 200,
            "total_budget_usd": [999.0] * 200,
            "daily_budget_usd": [33.3] * 200,
        })

    @pytest.fixture
    def impressions(self, campaigns):
        # every campaign delivers exactly 100.0, so the resulting budget is a
        # pure function of the drawn target ratio
        return pd.DataFrame({
            "campaign_id": list(campaigns["campaign_id"]) * 10,
            "revenue_usd": [10.0] * (len(campaigns) * 10),
        })

    def test_delivery_ratio_centres_near_one(self, rng, campaigns, impressions):
        out = gen.calibrate_budgets(rng, campaigns, impressions)
        ratio = 100.0 / out["total_budget_usd"]
        assert ratio.mean() == pytest.approx(1.0, abs=0.1)

    def test_outcomes_span_under_on_and_over_pacing(self, rng, campaigns, impressions):
        out = gen.calibrate_budgets(rng, campaigns, impressions)
        ratio = 100.0 / out["total_budget_usd"]
        assert (ratio < 0.9).any(), "no under-pacing campaigns"
        assert ((ratio >= 0.9) & (ratio <= 1.1)).any(), "no on-pace campaigns"
        assert (ratio > 1.1).any(), "no over-pacing campaigns"

    def test_a_campaign_with_no_delivery_still_gets_a_positive_budget(
        self, rng, campaigns, impressions
    ):
        # drop one campaign from the impressions entirely
        starved = impressions[impressions["campaign_id"] != "cmp_0000"]
        out = gen.calibrate_budgets(rng, campaigns, starved)
        budget = out.loc[out["campaign_id"] == "cmp_0000", "total_budget_usd"].iloc[0]
        assert budget > 0

    def test_daily_budget_is_consistent_with_total(self, rng, campaigns, impressions):
        out = gen.calibrate_budgets(rng, campaigns, impressions)
        expected = (out["total_budget_usd"] / out["flight_days"]).round(2)
        assert (out["daily_budget_usd"] == expected).all()


class TestFillRate:
    """The fill rate is an input. It must survive into the generated data."""

    @pytest.mark.parametrize("fill_rate", [0.5, 0.82, 0.95])
    def test_served_rate_matches_requested_rate(self, rng, subscribers, content, fill_rate):
        n = 20000
        requests = _requests_for(rng, subscribers, content, n, fill_rate)
        observed = requests["was_filled"].mean()
        # binomial sampling error at n=20000 is well under a percentage point
        assert observed == pytest.approx(fill_rate, abs=0.02)

    def test_default_fill_rate_is_the_published_figure(self):
        assert gen.DEFAULT_FILL_RATE == 0.82

    def test_default_is_used_when_no_rate_is_passed(self, rng, subscribers, content):
        requests = _requests_for(rng, subscribers, content, 20000)
        assert requests["was_filled"].mean() == pytest.approx(gen.DEFAULT_FILL_RATE, abs=0.02)


class TestImpressionsReconcileWithRequests:
    """
    The regression guard for the defect this file was written after: was_filled
    was drawn independently of whether an impression was actually created, so
    2% of requests claimed a fill that no impression backed.
    """

    @pytest.fixture
    def generated(self, rng, subscribers, content):
        requests = _requests_for(rng, subscribers, content, 5000, 0.82)
        # flights span the whole observation window so every impression date
        # has at least one campaign in flight
        campaigns = pd.DataFrame({
            "campaign_id": [f"cmp_{i:04d}" for i in range(20)],
            "advertiser_id": [f"adv_{i % 5:04d}" for i in range(20)],
            "total_budget_usd": [10000.0] * 20,
            "flight_start": [gen.DATASET_START] * 20,
            "flight_end": [gen.DATASET_END] * 20,
        })
        advertisers = pd.DataFrame({
            "advertiser_id": [f"adv_{i:04d}" for i in range(5)],
            "industry_vertical": ["Retail", "Finance", "Technology", "CPG", "QSR"],
        })
        impressions, served = gen.generate_impressions(rng, requests, campaigns, advertisers)
        return requests, impressions, served

    def test_every_filled_request_produces_an_impression(self, generated):
        requests, impressions, _ = generated
        filled = set(requests.loc[requests["was_filled"], "request_id"])
        assert set(impressions["request_id"]) == filled

    def test_impression_count_equals_filled_request_count(self, generated):
        requests, impressions, _ = generated
        assert len(impressions) == int(requests["was_filled"].sum())

    def test_no_impression_belongs_to_an_unfilled_request(self, generated):
        requests, impressions, _ = generated
        unfilled = set(requests.loc[~requests["was_filled"], "request_id"])
        assert not set(impressions["request_id"]) & unfilled

    def test_served_ids_match_the_impressions_returned(self, generated):
        _, impressions, served = generated
        assert served == set(impressions["request_id"])

    def test_request_ids_are_unique(self, generated):
        requests, _, _ = generated
        assert requests["request_id"].is_unique


class TestImpressionsFallInsideCampaignFlights:
    """
    An impression may only be attributed to a campaign that was in flight on
    that day. Campaigns were previously drawn from the whole catalog by budget
    weight with no reference to the date, which put 43% of campaign-days before
    their own flight start. A budget-delivery pacing metric cannot tolerate
    that: spend outside the flight has no share of budget to measure against,
    and the ratio goes negative.
    """

    @pytest.fixture
    def staggered(self, rng, subscribers, content):
        requests = _requests_for(rng, subscribers, content, 4000, 0.82)
        # deliberately staggered and short flights, so a date-blind assignment
        # would land outside a window almost every time
        starts = [gen.DATASET_START + timedelta(days=7 * i) for i in range(12)]
        campaigns = pd.DataFrame({
            "campaign_id": [f"cmp_{i:04d}" for i in range(12)],
            "advertiser_id": [f"adv_{i % 4:04d}" for i in range(12)],
            "total_budget_usd": [5000.0 * (i + 1) for i in range(12)],
            "flight_start": starts,
            "flight_end": [s + timedelta(days=20) for s in starts],
        })
        advertisers = pd.DataFrame({
            "advertiser_id": [f"adv_{i:04d}" for i in range(4)],
            "industry_vertical": ["Retail", "Finance", "Technology", "CPG"],
        })
        impressions, _ = gen.generate_impressions(rng, requests, campaigns, advertisers)
        return impressions, campaigns

    def test_every_impression_is_inside_its_campaign_flight(self, staggered):
        impressions, campaigns = staggered
        merged = impressions.merge(campaigns, on="campaign_id", how="left")
        day = pd.to_datetime(merged["impression_timestamp"]).dt.normalize()
        assert (day >= pd.to_datetime(merged["flight_start"])).all()
        assert (day <= pd.to_datetime(merged["flight_end"])).all()

    def test_assignment_is_still_budget_weighted_within_a_day(self, staggered):
        # the largest campaign overlapping the busiest stretch should not be
        # starved: date-awareness must not flatten the budget weighting
        impressions, _ = staggered
        counts = impressions["campaign_id"].value_counts()
        assert counts.max() > counts.min()

    def test_raises_rather_than_dropping_when_no_campaign_is_in_flight(
        self, rng, subscribers, content
    ):
        requests = _requests_for(rng, subscribers, content, 200, 0.82)
        far_future = gen.DATASET_END + timedelta(days=365)
        campaigns = pd.DataFrame({
            "campaign_id": ["cmp_0000"],
            "advertiser_id": ["adv_0000"],
            "total_budget_usd": [5000.0],
            "flight_start": [far_future],
            "flight_end": [far_future + timedelta(days=10)],
        })
        advertisers = pd.DataFrame({
            "advertiser_id": ["adv_0000"], "industry_vertical": ["Retail"],
        })
        with pytest.raises(ValueError, match="no campaign in flight"):
            gen.generate_impressions(rng, requests, campaigns, advertisers)
