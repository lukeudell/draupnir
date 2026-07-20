# ============================================================
#  file:       app/theme.py
#  purpose:    palette resolution with a strict hex allowlist against CSS injection
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-05]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Draupnir: Streamlit theme resolution.

The parent site owns the color palette. When this app is embedded, the active
scheme's colors arrive via the iframe URL query string. This module is the
single security choke point: every incoming value is validated against a strict
``#RRGGBB`` allowlist before it can reach any CSS or Plotly output, so
unvalidated input never flows into ``unsafe_allow_html``. A direct visit with no
query params falls back to the default palette.

Dependency-free (stdlib only) so it is unit-testable without Streamlit or pandas.

TECH DEBT: this module is duplicated rather than packaged, so each app image
stays self-contained with no shared build context. That is a deliberate
trade-off rather than an oversight, but it is worth revisiting: the honest
options are a shared package or an explicit acceptance of the duplication.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# The nine palette tokens forwarded by the frontend. Keys match the query-param
# names and the frontend `--color-<token>` CSS variables.
TOKENS: tuple[str, ...] = (
    "bg", "surface", "border", "cyan", "pink", "violet", "green", "amber", "white",
)

# Mirrors the TERMINAL palette in global.css (the site default), so a direct
# visit with no params matches the rest of the site (not the legacy purple).
DEFAULT_COLORS: dict[str, str] = {
    "bg": "#050505",
    "surface": "#121212",
    "border": "#262626",
    "cyan": "#00E5FF",
    "pink": "#FF2D95",
    "violet": "#D90429",
    "green": "#3DDC97",
    "amber": "#FFB703",
    "white": "#E8E8E8",
}

# Allowlist: a 6-digit hex color and nothing else. Matched with fullmatch() so
# the ENTIRE value must be hex. Note Python's ``$`` also matches just before a
# trailing newline, so ``re.match(r"...$", "#000000\n")`` would wrongly pass;
# fullmatch() does not have that footgun.
_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def _is_hex(value: Any) -> bool:
    """True only for a strict ``#RRGGBB`` string (whole string, no trailing chars)."""
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def _normalize(colors: Mapping[str, Any] | None) -> dict[str, str]:
    """Return a complete color map: terminal defaults with valid overrides applied.

    Only the nine known TOKENS are read; unknown keys are ignored. Any value that
    is not strict ``#RRGGBB`` is discarded in favor of the default. Two semantic
    aliases are derived (never taken from raw input):
      * ``text``  → ``white`` (Plotly font / chart text color)
      * ``red``   → ``pink``  (danger hue; adapts across schemes incl. safe mode)
    """
    resolved = dict(DEFAULT_COLORS)
    if colors:
        for token in TOKENS:
            value = colors.get(token)
            if _is_hex(value):
                resolved[token] = value
    resolved["text"] = resolved["white"]
    resolved["red"] = resolved["pink"]
    return resolved


def resolve_colors(query_params: Mapping[str, Any] | None) -> dict[str, str]:
    """Resolve the active color map from URL query params.

    For each known token, use the supplied value ONLY if it is a strict
    ``#RRGGBB`` string; otherwise fall back to the terminal default. This is the
    guarantee that only validated hex ever reaches CSS / chart output.
    """
    incoming: dict[str, Any] = {}
    if query_params:
        for token in TOKENS:
            try:
                value = query_params.get(token)
            except Exception:  # noqa: BLE001 (defensive against odd param objects)
                value = None
            if value is not None:
                incoming[token] = value
    return _normalize(incoming)


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert a validated ``#RRGGBB`` to an ``rgba(...)`` string for chart fills.

    Falls back to the default green if the input isn't strict hex, and clamps
    alpha to [0, 1]. Output is composed only from integers; no raw input.
    """
    if not _is_hex(hex_color):
        hex_color = DEFAULT_COLORS["green"]
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    a = min(max(float(alpha), 0.0), 1.0)
    return f"rgba({r}, {g}, {b}, {a})"


def plotly_layout(colors: Mapping[str, Any]) -> dict[str, Any]:
    """Build the shared Plotly layout dict from a (re-validated) color map."""
    c = _normalize(colors)
    return dict(
        paper_bgcolor=c["bg"],
        plot_bgcolor=c["surface"],
        font=dict(family="JetBrains Mono, monospace", color=c["white"]),
        margin=dict(l=40, r=40, t=50, b=40),
    )


def build_app_css(colors: Mapping[str, Any]) -> str:
    """Build the injected ``<style>`` block from a (re-validated) color map.

    Re-normalizes its input as defense in depth, so even a direct call with a
    malformed dict cannot emit anything but validated hex.
    """
    c = _normalize(colors)
    return f"""
    <style>
    .stApp {{ background-color: {c['bg']}; }}
    h1, h2, h3 {{ font-family: 'Share Tech Mono', monospace; }}
    .metric-label {{ color: {c['cyan']}; font-family: 'JetBrains Mono', monospace;
                    font-size: 0.8rem; text-transform: uppercase; }}
    .metric-value {{ color: {c['green']}; font-family: 'JetBrains Mono', monospace;
                    font-size: 1.4rem; font-weight: bold; white-space: nowrap;
                    overflow: hidden; text-overflow: ellipsis; max-width: 100%; }}
    .metric-card {{
        background: {c['surface']}; border: 1px solid {c['violet']};
        border-radius: 8px; padding: 0.75rem 0.5rem; text-align: center;
        min-height: 80px; display: flex; flex-direction: column;
        justify-content: center; align-items: center; overflow: hidden;
    }}
    .conflict-badge {{
        background: {c['red']}; color: {c['white']}; padding: 2px 8px;
        border-radius: 4px; font-size: 0.75rem; font-weight: bold;
    }}
    div[data-testid="stSlider"] label {{ color: {c['cyan']} !important; }}
    </style>
    """
