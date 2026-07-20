# ============================================================
#  file:       app/tests/test_metrics.py
#  purpose:    tests for the published metric thresholds and banding
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-02]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Tests for metric banding and presentation arithmetic.

The project's whole subject is metric definitions, and until now not one of them
had a test. These assert the published thresholds directly, including the
boundaries, because a band that is right in the middle and wrong at the edge is
the kind of error a dashboard never reveals.

Loads the sibling module by explicit path so the suite does not depend on
sys.path or the pytest rootdir.
"""

import importlib.util
import pathlib

import pytest

_MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent / "metrics.py"
_spec = importlib.util.spec_from_file_location("metrics", _MODULE_PATH)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


class TestBand:
    def test_none_is_unknown_not_a_pass(self):
        assert m.band(None, m.FILL_RATE_PCT) == m.UNKNOWN

    def test_catch_all_entry_matches_anything_remaining(self):
        assert m.band(10_000.0, m.ECPM_USD) == m.GOOD

    @pytest.mark.parametrize("thresholds", [
        m.FILL_RATE_PCT, m.ECPM_USD, m.VIEWABILITY_PCT, m.FREQUENCY_VIOLATION_PCT, m.RPSH_USD,
    ])
    def test_every_table_ends_with_a_catch_all(self, thresholds):
        assert thresholds[-1][0] is None, "a value above every bound would be UNKNOWN"

    @pytest.mark.parametrize("thresholds", [
        m.FILL_RATE_PCT, m.ECPM_USD, m.VIEWABILITY_PCT, m.FREQUENCY_VIOLATION_PCT, m.RPSH_USD,
    ])
    def test_bounds_ascend(self, thresholds):
        bounds = [b for b, _ in thresholds if b is not None]
        assert bounds == sorted(bounds), "out-of-order bounds make earlier rows unreachable"


class TestFillRate:
    """Published: <70 investigate, 80-90 healthy, >95 supply constrained."""

    @pytest.mark.parametrize("value,expected", [
        (0.0, m.BAD), (69.9, m.BAD),
        (70.0, m.WARN), (79.9, m.WARN),
        (80.0, m.GOOD), (85.0, m.GOOD), (89.9, m.GOOD),
        (90.0, m.WARN), (96.0, m.WARN), (100.0, m.WARN),
    ])
    def test_bands(self, value, expected):
        assert m.band(value, m.FILL_RATE_PCT) == expected

    def test_the_measured_platform_rate_is_healthy(self):
        # the generator targets 82% and the marts observe ~81.8
        assert m.band(81.8, m.FILL_RATE_PCT) == m.GOOD


class TestEcpm:
    """Published: <$8 below market, $12-25 healthy, >$30 premium."""

    @pytest.mark.parametrize("value,expected", [
        (0.0, m.BAD), (7.99, m.BAD),
        (8.0, m.WARN), (11.99, m.WARN),
        (12.0, m.GOOD), (24.99, m.GOOD), (40.0, m.GOOD),
    ])
    def test_bands(self, value, expected):
        assert m.band(value, m.ECPM_USD) == expected


class TestViewability:
    """Published: <60 below standard, ~70 benchmark, >80 premium."""

    @pytest.mark.parametrize("value,expected", [
        (0.0, m.BAD), (59.9, m.BAD),
        (60.0, m.WARN), (69.9, m.WARN),
        (70.0, m.GOOD), (95.0, m.GOOD),
    ])
    def test_bands(self, value, expected):
        assert m.band(value, m.VIEWABILITY_PCT) == expected


class TestFrequencyViolation:
    """Published: <2% target, 2-5% investigate, >5% ad fatigue. Lower is better."""

    @pytest.mark.parametrize("value,expected", [
        (0.0, m.GOOD), (1.99, m.GOOD),
        (2.0, m.WARN), (4.99, m.WARN),
        (5.0, m.BAD), (100.0, m.BAD),
    ])
    def test_bands(self, value, expected):
        assert m.band(value, m.FREQUENCY_VIOLATION_PCT) == expected

    def test_direction_is_inverted_relative_to_the_other_metrics(self):
        # guards against someone "tidying" this table to match the others
        assert m.band(0.0, m.FREQUENCY_VIOLATION_PCT) == m.GOOD
        assert m.band(99.0, m.FREQUENCY_VIOLATION_PCT) == m.BAD


class TestRpsh:
    """
    RPSH is the only metric here that is bad in both directions: too low wastes
    inventory, too high means an ad load viewers will leave over. The catalog
    used to publish $2 / $4 / $6 per hour, which no real platform can reach, so
    these bounds are derived from ad load times eCPM instead.
    """

    @pytest.mark.parametrize("value,expected", [
        (0.0, m.BAD), (0.149, m.BAD),
        (0.15, m.GOOD), (0.2377, m.GOOD), (0.349, m.GOOD),
        (0.35, m.WARN), (1.0, m.WARN),
    ])
    def test_bands(self, value, expected):
        assert m.band(value, m.RPSH_USD) == expected

    def test_the_measured_platform_rate_is_healthy(self):
        # the warehouse observes ~$0.238 per viewing hour at ~8.5 ads/hour
        assert m.band(0.2377, m.RPSH_USD) == m.GOOD

    def test_the_old_published_thresholds_would_all_read_as_churn_risk(self):
        # documents why they were corrected rather than carried forward: every
        # one of them sits far outside anything the arithmetic can produce
        for unreachable in (2.0, 4.0, 6.0):
            assert m.band(unreachable, m.RPSH_USD) == m.WARN

    def test_is_not_monotonic_unlike_the_other_metrics(self):
        assert m.band(0.05, m.RPSH_USD) == m.BAD
        assert m.band(0.25, m.RPSH_USD) == m.GOOD
        assert m.band(0.90, m.RPSH_USD) != m.GOOD

    def test_missing_value_is_unknown(self):
        assert m.band(None, m.RPSH_USD) == m.UNKNOWN


class TestWarehouseComputedVerdicts:
    """This module translates these labels; it must never recompute them."""

    @pytest.mark.parametrize("status,expected", [
        ("ON_PACE", m.GOOD), ("OVER_PACING", m.WARN),
        ("UNDER_PACING", m.BAD), ("UNKNOWN", m.UNKNOWN),
    ])
    def test_pacing_status(self, status, expected):
        assert m.verdict_for_status(status, m.PACING_STATUS_VERDICT) == expected

    @pytest.mark.parametrize("band_name,expected", [
        ("DIVERSIFIED", m.GOOD), ("MODERATE", m.WARN), ("CONCENTRATED", m.BAD),
    ])
    def test_concentration(self, band_name, expected):
        assert m.verdict_for_status(band_name, m.CONCENTRATION_VERDICT) == expected

    def test_unrecognised_label_is_unknown_not_a_pass(self):
        assert m.verdict_for_status("SOMETHING_NEW", m.PACING_STATUS_VERDICT) == m.UNKNOWN

    def test_none_is_unknown(self):
        assert m.verdict_for_status(None, m.PACING_STATUS_VERDICT) == m.UNKNOWN

    def test_pacing_vocabulary_matches_the_warehouse(self):
        # these are the accepted_values enforced on pacing_status in schema.yml
        assert set(m.PACING_STATUS_VERDICT) == {
            "ON_PACE", "UNDER_PACING", "OVER_PACING", "UNKNOWN",
        }

    def test_concentration_vocabulary_matches_the_warehouse(self):
        assert set(m.CONCENTRATION_VERDICT) == {
            "DIVERSIFIED", "MODERATE", "CONCENTRATED",
        }


class TestVerdictColor:
    COLORS = {"green": "#0f0", "amber": "#fa0", "red": "#f00"}

    def test_maps_each_verdict(self):
        assert m.verdict_color(m.GOOD, self.COLORS) == "#0f0"
        assert m.verdict_color(m.WARN, self.COLORS) == "#fa0"
        assert m.verdict_color(m.BAD, self.COLORS) == "#f00"

    def test_unknown_is_neutral_not_alarming(self):
        assert m.verdict_color(m.UNKNOWN, self.COLORS) == "#fa0"

    def test_missing_palette_key_does_not_raise(self):
        assert m.verdict_color(m.GOOD, {}) == ""


class TestPlannedSpendCurve:
    def test_reaches_exactly_the_budget_on_the_final_day(self):
        days, spend = m.planned_spend_curve(1000.0, 30)
        assert days[-1] == 30
        assert spend[-1] == pytest.approx(1000.0)

    def test_starts_at_one_day_of_budget_not_zero(self):
        _, spend = m.planned_spend_curve(1000.0, 10)
        assert spend[0] == pytest.approx(100.0)

    def test_is_linear(self):
        _, spend = m.planned_spend_curve(900.0, 9)
        steps = [b - a for a, b in zip(spend, spend[1:])]
        assert all(s == pytest.approx(steps[0]) for s in steps)

    def test_single_day_flight(self):
        days, spend = m.planned_spend_curve(500.0, 1)
        assert days == [1]
        assert spend == [pytest.approx(500.0)]

    def test_rejects_a_zero_length_flight(self):
        with pytest.raises(ValueError, match="at least 1"):
            m.planned_spend_curve(1000.0, 0)


class TestFormatMetric:
    def test_formats_a_value(self):
        assert m.format_metric(81.83, "{:.1f}") == "81.8"

    def test_missing_value_is_not_zero(self):
        assert m.format_metric(None) == "n/a"
        assert "0" not in m.format_metric(None)

    def test_custom_fallback(self):
        assert m.format_metric(None, fallback="unknown") == "unknown"

    def test_bad_format_string_falls_back_rather_than_raising(self):
        assert m.format_metric("abc", "{:.2f}") == "n/a"
