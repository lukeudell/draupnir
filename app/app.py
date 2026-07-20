# ============================================================
#  file:       app/app.py
#  purpose:    campaign pacing monitor: streamlit dashboard over the ads analytics layer
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-01] [STD-05]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Draupnir: Campaign Pacing Monitor
Interactive ad platform health dashboard and campaign pacing tool.
Self-hosted Streamlit application with vaporwave aesthetic.
"""

import html

import plotly.graph_objects as go
import streamlit as st

import db
import metrics
from theme import build_app_css, hex_to_rgba, plotly_layout, resolve_colors

st.set_page_config(
    page_title="Campaign Pacing Monitor | Draupnir",
    page_icon="📊",
    layout="wide",
)

# Theme colors are resolved from the iframe URL query string. The parent site
# forwards the active palette so the demo matches whatever scheme is active.
# resolve_colors validates every value against a strict hex allowlist (theme.py);
# a direct visit with no params falls back to the site-default terminal palette.
COLORS = resolve_colors(st.query_params)
PLOTLY_LAYOUT = plotly_layout(COLORS)


class _Unavailable(Exception):
    """Raised inside the cache so that a failed read is not what gets cached."""


@st.cache_data(ttl=300)
def _load_cached(name: str):
    # why: st.cache_data stores return values but not exceptions, so raising on
    # failure is what keeps the offline state out of the cache. Returning None
    # here would pin the dashboard offline for the full TTL after the database
    # came back, which turns a ten-second outage into a five-minute one.
    result = db.fetch(name)
    if result is None:
        raise _Unavailable(name)
    return result


def load(name: str):
    """Read one analytics table, or None if the warehouse cannot be read.

    None is the offline signal and is never substituted with stand-in data;
    see the contract in db.py. Successful reads are cached for five minutes,
    failures are not, so recovery is picked up on the next rerun.
    """
    try:
        return _load_cached(name)
    except _Unavailable:
        return None


def offline_notice(what: str) -> None:
    """Render the explicit empty state for a section with no data."""
    st.warning(
        f"**Offline.** {what} could not be read from the warehouse, so nothing "
        "is shown here. No figures on this page are simulated."
    )


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
# SECURITY: unsafe_allow_html=True is used below for CSS theming and styled
# metric cards. The CSS is built by theme.build_app_css() from query-param-derived
# colors validated against a strict ``#RRGGBB`` allowlist, so no raw user input
# reaches it. Metric-card HTML uses hardcoded templates interpolating only
# formatted numbers, those validated colors, and strings passed through
# html.escape(). Nothing from the database is rendered raw: the label vocabularies
# are enforced in SQL today, but an app that is safe only because of an upstream
# invariant it does not check is one schema change from stored XSS. See SECURITY.md.

st.markdown(build_app_css(COLORS), unsafe_allow_html=True)

# why: this app is designed to be embedded in a page that already has its own
# navigation, so Streamlit's own toolbar, main menu and footer are chrome the
# surrounding site does not want and cannot style. Hidden here rather than in
# theme.py, which stays palette-only and is shared with the other apps: how this
# one is framed is its own concern. Static selectors and no interpolation, so
# nothing user-supplied reaches this string.
st.markdown(
    """
    <style>
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("CAMPAIGN PACING MONITOR")
st.markdown("*Ad platform health, campaign delivery, frequency analysis, and advertiser mix.*")

tab1, tab2, tab3, tab4 = st.tabs(["PLATFORM HEALTH", "CAMPAIGN PACING", "FREQUENCY & REACH", "ADVERTISER MIX"])

# ===== TAB 1: PLATFORM HEALTH =====
with tab1:
    health = load("platform_health")
    if health is None or health.empty:
        offline_notice("Platform health")
    else:
        latest = health.iloc[-1]
        # thresholds come from metrics.py; a metric with no published band shows
        # its value uncoloured rather than being given an invented verdict.
        cards = [
            ("Fill Rate", "fill_rate_pct", "{:.1f}%", metrics.FILL_RATE_PCT),
            ("eCPM", "ecpm_usd", "${:.2f}", metrics.ECPM_USD),
            ("Completion", "completion_rate_pct", "{:.1f}%", None),
            ("Viewability", "viewability_rate_pct", "{:.1f}%", metrics.VIEWABILITY_PCT),
            ("RPSH", "revenue_per_subscriber_hour", "${:.3f}", metrics.RPSH_USD),
            ("Daily Revenue", "total_revenue_usd", "${:,.0f}", None),
        ]
        for col, (label, column, fmt, thresholds) in zip(st.columns(len(cards)), cards):
            value = metrics.optional_number(latest.get(column))
            style = ""
            if thresholds is not None:
                style = f'style="color:{metrics.verdict_color(metrics.band(value, thresholds), COLORS)}"'
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div>'
                            f'<div class="metric-value" {style}>'
                            f'{metrics.format_metric(value, fmt)}</div></div>',
                            unsafe_allow_html=True)

        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=health["full_date"], y=health["fill_rate_pct"],
                                     name="Fill Rate %", line=dict(color=COLORS["cyan"], width=2)))
            fig.update_layout(**PLOTLY_LAYOUT, title="Fill Rate Trend", height=350,
                             xaxis_title="Date", yaxis_title="%")
            fig.update_xaxes(gridcolor=COLORS["border"])
            fig.update_yaxes(gridcolor=COLORS["border"])
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=health["full_date"], y=health["total_revenue_usd"],
                                     name="Revenue", line=dict(color=COLORS["green"], width=2),
                                     fill="tozeroy", fillcolor=hex_to_rgba(COLORS["green"], 0.1)))
            fig.update_layout(**PLOTLY_LAYOUT, title="Daily Revenue", height=350,
                             xaxis_title="Date", yaxis_title="USD")
            fig.update_xaxes(gridcolor=COLORS["border"])
            fig.update_yaxes(gridcolor=COLORS["border"])
            st.plotly_chart(fig, use_container_width=True)

# ===== TAB 2: CAMPAIGN PACING =====
with tab2:
    perf = load("campaign_performance")
    if perf is None or perf.empty:
        offline_notice("Campaign performance")
    else:

        campaigns = perf[["campaign_key", "campaign_name", "company_name"]].drop_duplicates()
        # why: a dict lookup, not a DataFrame filter per option. format_func runs
        # once per rendered option on every rerun, so filtering inside it made the
        # widget quadratic in campaign count: ~500 options each scanning ~500 rows,
        # repeated on every interaction, and a visitor can trigger reruns freely.
        campaign_names = dict(zip(campaigns["campaign_key"], campaigns["campaign_name"]))
        selected = st.selectbox("Select Campaign", list(campaign_names),
                                format_func=lambda x: f"{x}: {campaign_names.get(x, '')}")

        camp_data = perf[perf["campaign_key"] == selected].sort_values("date_key")
        if not camp_data.empty:
            latest_camp = camp_data.iloc[-1]
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(f'<div class="metric-card"><div class="metric-label">Budget</div>'
                            f'<div class="metric-value">${latest_camp.get("total_budget_usd",0):,.0f}</div></div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="metric-card"><div class="metric-label">Spent</div>'
                            f'<div class="metric-value">${latest_camp.get("cumulative_spend",0):,.0f}</div></div>', unsafe_allow_html=True)
            with col3:
                # a missing ratio is unknown, not zero: rendering 0.00 in red
                # would report catastrophic under-delivery for missing data.
                ratio = metrics.optional_number(latest_camp.get("budget_pacing_ratio"))
                color = metrics.verdict_color(
                    metrics.verdict_for_status(
                        latest_camp.get("pacing_status"), metrics.PACING_STATUS_VERDICT
                    ),
                    COLORS,
                )
                st.markdown(f'<div class="metric-card"><div class="metric-label">Pacing Ratio</div>'
                            f'<div class="metric-value" style="color:{color}">'
                            f'{metrics.format_metric(ratio, "{:.2f}")}</div></div>',
                            unsafe_allow_html=True)
            with col4:
                status = latest_camp.get("pacing_status", "UNKNOWN")
                sc = {
                    "ON_PACE": COLORS["green"],
                    "UNDER_PACING": COLORS["red"],
                    "OVER_PACING": COLORS["amber"],
                }.get(status, COLORS["amber"])
                st.markdown(f'<div class="metric-card"><div class="metric-label">Status</div>'
                            f'<div class="metric-value" style="color:{sc};font-size:1rem">'
                            f'{html.escape(str(status))}</div></div>', unsafe_allow_html=True)

            st.markdown("---")
            # Pacing chart
            fig = go.Figure()
            budget = latest_camp.get("total_budget_usd", 1)
            flight = latest_camp.get("flight_days", 1)
            planned_x, planned_y = metrics.planned_spend_curve(budget, max(int(flight), 1))
            fig.add_trace(go.Scatter(x=planned_x, y=planned_y, name="Planned Spend",
                                     line=dict(color=COLORS["violet"], width=2, dash="dash")))
            fig.add_trace(go.Scatter(x=camp_data["elapsed_days"], y=camp_data["cumulative_spend"],
                                     name="Actual Spend", line=dict(color=COLORS["cyan"], width=3)))
            fig.update_layout(**PLOTLY_LAYOUT, title="Campaign Pacing: Planned vs Actual", height=400,
                             xaxis_title="Day of Flight", yaxis_title="Cumulative USD")
            fig.update_xaxes(gridcolor=COLORS["border"])
            fig.update_yaxes(gridcolor=COLORS["border"])
            st.plotly_chart(fig, use_container_width=True)

# ===== TAB 3: FREQUENCY & REACH =====
with tab3:
    freq = load("frequency_analysis")
    if freq is None or freq.empty:
        offline_notice("Frequency analysis")
    else:

        col1, col2, col3 = st.columns(3)
        avg_violation = freq["violation_rate_pct"].mean()
        avg_freq = freq["avg_frequency"].mean()
        with col1:
            vc = metrics.verdict_color(
                metrics.band(avg_violation, metrics.FREQUENCY_VIOLATION_PCT), COLORS
            )
            st.markdown(f'<div class="metric-card"><div class="metric-label">Avg Violation Rate</div>'
                        f'<div class="metric-value" style="color:{vc}">'
                        f'{metrics.format_metric(avg_violation)}%</div></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Avg Frequency</div>'
                        f'<div class="metric-value">{avg_freq:.1f}x</div></div>', unsafe_allow_html=True)
        with col3:
            total_subs = freq["total_subscribers"].sum()
            st.markdown(f'<div class="metric-card"><div class="metric-label">Total Reach</div>'
                        f'<div class="metric-value">{total_subs:,}</div></div>', unsafe_allow_html=True)

        st.markdown("---")
        fig = go.Figure(data=[go.Bar(
            x=freq["campaign_name"] if "campaign_name" in freq.columns else freq["campaign_key"],
            y=freq["violation_rate_pct"],
            marker={"color": [
                metrics.verdict_color(
                    metrics.band(metrics.optional_number(v), metrics.FREQUENCY_VIOLATION_PCT),
                    COLORS,
                )
                for v in freq["violation_rate_pct"]
            ]},
        )])
        fig.update_layout(**PLOTLY_LAYOUT, title="Frequency Cap Violation Rate by Campaign",
                         height=400, xaxis_title="Campaign", yaxis_title="Violation %", showlegend=False)
        fig.update_xaxes(gridcolor=COLORS["border"], tickangle=45)
        fig.update_yaxes(gridcolor=COLORS["border"])
        st.plotly_chart(fig, use_container_width=True)

# ===== TAB 4: ADVERTISER MIX =====
with tab4:
    advs = load("advertiser_summary")
    if advs is None or advs.empty:
        offline_notice("Advertiser summary")
    else:

        # HHI is computed in the analytics layer, not here: it is a business metric
        # with regulatory thresholds, and it belongs somewhere testable and readable
        # by anything that is not this dashboard.
        conc = load("advertiser_concentration")
        if conc is None or conc.empty:
            hhi, hhi_status, advertiser_count = None, None, len(advs)
        else:
            row = conc.iloc[0]
            hhi = float(row["hhi"])
            hhi_status = row["concentration_band"]
            advertiser_count = int(row["advertiser_count"])
        hhi_color = metrics.verdict_color(
            metrics.verdict_for_status(hhi_status, metrics.CONCENTRATION_VERDICT), COLORS
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">HHI Score</div>'
                        f'<div class="metric-value" style="color:{hhi_color}">'
                        f'{metrics.format_metric(hhi, "{:.0f}")}</div></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Concentration</div>'
                        f'<div class="metric-value" style="color:{hhi_color};font-size:1rem">'
                        f'{html.escape(str(hhi_status)) if hhi_status else "n/a"}</div></div>',
                        unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Advertisers</div>'
                        f'<div class="metric-value">{advertiser_count}</div></div>', unsafe_allow_html=True)

        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            top10 = advs.head(10)
            fig = go.Figure(data=[go.Bar(x=top10["company_name"], y=top10["total_spend"],
                                         marker=dict(color=COLORS["cyan"]))])
            fig.update_layout(**PLOTLY_LAYOUT, title="Top 10 Advertisers by Spend", height=400,
                             xaxis_title="Advertiser", yaxis_title="USD", showlegend=False)
            fig.update_xaxes(gridcolor=COLORS["border"], tickangle=45)
            fig.update_yaxes(gridcolor=COLORS["border"])
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            by_vert = advs.groupby("industry_vertical")["total_spend"].sum().reset_index()
            fig = go.Figure(data=[go.Pie(labels=by_vert["industry_vertical"], values=by_vert["total_spend"],
                                         marker=dict(colors=[COLORS["cyan"], COLORS["pink"], COLORS["green"],
                                                            COLORS["amber"], COLORS["violet"]] * 2),
                                         textinfo="label+percent", textfont=dict(color=COLORS["text"]), hole=0.4)])
            fig.update_layout(**PLOTLY_LAYOUT, title="Revenue by Vertical", height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown(f'<div style="text-align:center;color:{COLORS["violet"]};font-size:0.8rem;">'
                'COMMAND CENTER // Campaign Pacing Monitor v0.1.0 // lukeudell.com</div>', unsafe_allow_html=True)
