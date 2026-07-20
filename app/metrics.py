# ============================================================
#  file:       app/metrics.py
#  purpose:    the published metric thresholds, as executable definitions
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-02] [STD-03]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Threshold banding and presentation arithmetic for the pacing monitor.

Every band in the published metrics catalog lived as an inline conditional in
``app.py``, repeated per tab and untested. A project whose subject is metric
definitions should not have its definitions scattered through render code, so
they live here as data, and the catalog becomes something that can be asserted
rather than only read.

Division of responsibility, to avoid a second source of truth ([STD-03]):

- Where the warehouse already models a verdict, it owns it. ``pacing_status``
  and ``concentration_band`` are computed in SQL, and this module only maps the
  resulting label to a display colour. It never recomputes them.
- Where the warehouse emits a bare number and the banding is presentation
  (fill rate, eCPM, viewability, frequency violations), this module owns the
  thresholds.

Dependency-free (stdlib only) so it is unit-testable without Streamlit or
pandas, and so the thresholds can be imported by anything that needs them.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

# Verdict vocabulary. Ordered worst to best is deliberate: it keeps the mapping
# to colours obvious and stops a caller inventing its own strings.
GOOD = "good"
WARN = "warn"
BAD = "bad"
UNKNOWN = "unknown"

# Published thresholds. Each entry is a list of (upper_bound, verdict) pairs
# evaluated in order, with the final entry acting as the catch-all. Keeping them
# as data rather than nested conditionals is what makes them assertable.
FILL_RATE_PCT = [(70.0, BAD), (80.0, WARN), (90.0, GOOD), (95.0, WARN), (None, WARN)]
ECPM_USD = [(8.0, BAD), (12.0, WARN), (25.0, GOOD), (None, GOOD)]
VIEWABILITY_PCT = [(60.0, BAD), (70.0, WARN), (None, GOOD)]
FREQUENCY_VIOLATION_PCT = [(2.0, GOOD), (5.0, WARN), (None, BAD)]

# Revenue per subscriber hour. Unlike the others this is not monotonic: too low
# means inventory is under-monetised, too high means viewers are being shown
# more advertising than they will tolerate, so the healthy state is the middle.
#
# The bounds are derived rather than asserted. RPSH is ad load per hour times
# eCPM over 1000, so at the platform's ~$25 eCPM:
#   6 ads/hour  -> $0.15    below this, inventory is being wasted
#   14 ads/hour -> $0.35    above this, ad load is into churn territory
# The catalog previously published $2 / $4 / $6 per hour. That would need 160
# impressions in a viewing hour, an ad every 22 seconds, so it was unreachable
# by any real platform and is corrected here rather than carried forward.
RPSH_USD = [(0.15, BAD), (0.35, GOOD), (None, WARN)]

# Verdicts the warehouse computes. This module classifies nothing here; it only
# translates a label the SQL already decided.
PACING_STATUS_VERDICT = {
    "ON_PACE": GOOD,
    "OVER_PACING": WARN,
    "UNDER_PACING": BAD,
    "UNKNOWN": UNKNOWN,
}
CONCENTRATION_VERDICT = {
    "DIVERSIFIED": GOOD,
    "MODERATE": WARN,
    "CONCENTRATED": BAD,
}


def band(value: float | None, thresholds: Sequence[tuple[float | None, str]]) -> str:
    """Classify a value against an ordered threshold table.

    Args:
        value: the measurement, or None when it could not be computed.
        thresholds: (upper_bound, verdict) pairs in ascending order. A bound of
            None matches anything remaining and must come last.

    Returns:
        One of GOOD, WARN, BAD, or UNKNOWN when value is None.
    """
    if value is None:
        return UNKNOWN
    for upper, verdict in thresholds:
        if upper is None or value < upper:
            return verdict
    return UNKNOWN


def verdict_for_status(status: str | None, mapping: dict[str, str]) -> str:
    """Translate a warehouse-computed status label into a display verdict.

    An unrecognised label is UNKNOWN rather than an assumed pass: a status this
    module has not been taught about is not evidence of health.
    """
    if status is None:
        return UNKNOWN
    return mapping.get(status, UNKNOWN)


def verdict_color(verdict: str, colors: dict[str, str]) -> str:
    """Map a verdict onto the active palette, defaulting to the neutral amber."""
    return {
        GOOD: colors.get("green", ""),
        WARN: colors.get("amber", ""),
        BAD: colors.get("red", ""),
    }.get(verdict, colors.get("amber", ""))


def planned_spend_curve(budget: float, flight_days: int) -> tuple[list[int], list[float]]:
    """Straight-line planned spend across a campaign flight.

    This is the reference line the delivery curve is read against, so it has to
    reach exactly the budget on the final day; an off-by-one here makes every
    campaign look slightly ahead of or behind plan.

    Args:
        budget: total campaign budget.
        flight_days: flight length in days. Must be at least 1.

    Returns:
        Day numbers (1-indexed) and the cumulative spend planned by each.

    Raises:
        ValueError: if flight_days is less than 1.
    """
    if flight_days < 1:
        raise ValueError(f"flight_days must be at least 1, got {flight_days}")
    days = list(range(1, flight_days + 1))
    return days, [budget * d / flight_days for d in days]


def optional_number(value) -> float | None:
    """Normalise a possibly-missing warehouse value to a float or None.

    A nullable numeric column arrives from pandas as NaN rather than None, and
    NaN silently poisons every comparison it touches: ``0.9 <= nan <= 1.1`` is
    False, so a missing value would quietly classify as out of band. Collapsing
    both spellings of "missing" to None here means the callers only handle one.

    Uses stdlib ``math.isnan`` rather than pandas or numpy, which keeps this
    module dependency-free and importable without either.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def format_metric(value: float | None, fmt: str = "{:.1f}", fallback: str = "n/a") -> str:
    """Format a metric for display, rendering a missing value as text.

    Missing metrics must never render as 0. A zero is a measurement and reads as
    catastrophic on most of these scales; "n/a" is the truth.
    """
    if value is None:
        return fallback
    try:
        return fmt.format(value)
    except (ValueError, TypeError):
        return fallback
