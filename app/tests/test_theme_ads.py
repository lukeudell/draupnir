# ============================================================
#  file:       app/tests/test_theme_ads.py
#  purpose:    tests for the palette resolver and its CSS injection defences
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-02] [STD-05]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Theme-resolution tests for the Campaign Pacing Monitor app.

Security-critical: the functions under test are the single choke point that
prevents query-param values from injecting into the apps' ``unsafe_allow_html``
CSS. Loads the sibling ``theme.py`` by explicit path so the suite is independent
of sys.path / pytest rootdir and never collides with the other apps' copies.
"""

import importlib.util
import pathlib

import pytest

_THEME_PATH = pathlib.Path(__file__).resolve().parent.parent / "theme.py"
_spec = importlib.util.spec_from_file_location("theme_ads", _THEME_PATH)
theme = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(theme)


# Injection / malformed payloads that must NEVER survive validation.
MALICIOUS = [
    "red;}</style><script>alert(1)</script>",
    "url(javascript:alert(1))",
    "expression(alert(1))",
    "#fff onload=alert(1)",
    "#fff",                  # short form
    "#0B0014;}body{display:none",
    "00E5FF",                # missing #
    "#00E5FG",               # non-hex digit
    "#00E5FFF",              # 7 digits
    "rgb(0,0,0)",
    "#" + "a" * 5000,        # overlong
    "",
]

# Payloads that carry CSS/HTML breakout characters. These must never appear in
# rendered output. (The benign-but-invalid entries above, e.g. "00E5FF", are
# excluded here: they fall back to a default whose hex they may coincidentally
# substring; their rejection is proven by the resolve_colors fallback tests.)
INJECTION = [
    "red;}</style><script>alert(1)</script>",
    "url(javascript:alert(1))",
    "expression(alert(1))",
    "#fff onload=alert(1)",
    "#0B0014;}body{display:none",
]


class TestIsHex:
    @pytest.mark.parametrize("value", ["#000000", "#FFFFFF", "#00e5ff", "#00E5FF"])
    def test_accepts_valid_six_digit_hex(self, value):
        assert theme._is_hex(value) is True

    @pytest.mark.parametrize("value", MALICIOUS + [None, 123, ["#000000"]])
    def test_rejects_everything_else(self, value):
        assert theme._is_hex(value) is False

    @pytest.mark.parametrize("value", ["#000000\n", "#000000\r\n", "#000000 ", " #000000"])
    def test_rejects_whitespace_padded_hex(self, value):
        # Guards the Python `$`-matches-before-trailing-newline footgun: fullmatch
        # must reject any value with leading/trailing characters.
        assert theme._is_hex(value) is False


class TestResolveColors:
    def test_none_params_returns_defaults(self):
        assert theme.resolve_colors(None) == theme._normalize({})

    def test_empty_params_returns_terminal_defaults(self):
        colors = theme.resolve_colors({})
        for token, expected in theme.DEFAULT_COLORS.items():
            assert colors[token] == expected

    def test_valid_overrides_are_applied_verbatim(self):
        colors = theme.resolve_colors({"bg": "#FFFFFF", "cyan": "#0057B7"})
        assert colors["bg"] == "#FFFFFF"
        assert colors["cyan"] == "#0057B7"
        assert colors["green"] == theme.DEFAULT_COLORS["green"]

    def test_supports_all_nine_tokens(self):
        override = dict.fromkeys(theme.TOKENS, "#123456")
        colors = theme.resolve_colors(override)
        for t in theme.TOKENS:
            assert colors[t] == "#123456"

    @pytest.mark.parametrize("payload", MALICIOUS)
    def test_malicious_values_fall_back_to_default(self, payload):
        colors = theme.resolve_colors({"bg": payload})
        assert colors["bg"] == theme.DEFAULT_COLORS["bg"]

    def test_unknown_params_are_ignored(self):
        colors = theme.resolve_colors({"evil": "#000000", "bg": "#FFFFFF"})
        assert "evil" not in colors
        assert colors["bg"] == "#FFFFFF"

    def test_derives_text_and_red_aliases(self):
        colors = theme.resolve_colors({"white": "#111111", "pink": "#222222"})
        assert colors["text"] == "#111111"
        assert colors["red"] == "#222222"

    def test_aliases_present_even_with_no_params(self):
        colors = theme.resolve_colors(None)
        assert colors["text"] == theme.DEFAULT_COLORS["white"]
        assert colors["red"] == theme.DEFAULT_COLORS["pink"]


class TestBuildAppCss:
    @pytest.mark.parametrize("payload", INJECTION)
    def test_malicious_input_never_appears_in_output(self, payload):
        css = theme.build_app_css({"bg": payload, "cyan": payload})
        assert payload == "" or payload not in css
        assert "<script" not in css.lower()
        assert "javascript:" not in css.lower()
        assert "expression(" not in css.lower()

    def test_output_contains_only_validated_hex_colors(self):
        css = theme.build_app_css(theme.resolve_colors({"bg": "#FFFFFF"}))
        assert "#FFFFFF" in css
        assert theme.DEFAULT_COLORS["cyan"] in css

    def test_no_legacy_purple_literals_leak_through(self):
        css = theme.build_app_css(theme.resolve_colors({}))
        for legacy in ("#0B0014", "#1A0A2E", "#7B2FBE", "#2A1A3E"):
            assert legacy not in css


class TestPlotlyLayout:
    def test_uses_supplied_colors(self):
        layout = theme.plotly_layout(theme.resolve_colors({"bg": "#010203", "surface": "#040506"}))
        assert layout["paper_bgcolor"] == "#010203"
        assert layout["plot_bgcolor"] == "#040506"

    def test_font_color_tracks_white_token(self):
        layout = theme.plotly_layout(theme.resolve_colors({"white": "#0A0B0C"}))
        assert layout["font"]["color"] == "#0A0B0C"

    @pytest.mark.parametrize("payload", MALICIOUS)
    def test_malicious_input_falls_back(self, payload):
        layout = theme.plotly_layout({"bg": payload})
        assert layout["paper_bgcolor"] == theme.DEFAULT_COLORS["bg"]


class TestHexToRgba:
    def test_converts_valid_hex(self):
        assert theme.hex_to_rgba("#000000", 0.1) == "rgba(0, 0, 0, 0.1)"
        assert theme.hex_to_rgba("#FFFFFF", 1.0) == "rgba(255, 255, 255, 1.0)"

    def test_clamps_alpha(self):
        assert theme.hex_to_rgba("#000000", 5) == "rgba(0, 0, 0, 1.0)"
        assert theme.hex_to_rgba("#000000", -1) == "rgba(0, 0, 0, 0.0)"

    @pytest.mark.parametrize("payload", MALICIOUS)
    def test_malicious_hex_falls_back_to_default_green(self, payload):
        out = theme.hex_to_rgba(payload, 0.1)
        assert payload == "" or payload not in out
        assert out.startswith("rgba(")
