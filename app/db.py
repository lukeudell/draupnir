# ============================================================
#  file:       app/db.py
#  purpose:    read-only warehouse access that degrades to None, never to fiction
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-05] [STD-14]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Analytics reads for the Campaign Pacing Monitor.

The dashboard previously caught every exception, showed a transient warning, and
then rendered `numpy`-generated stand-in numbers: fill rates around 82%, eCPM
around $25, a plausible spread of pacing statuses. A visitor who missed one line
of warning text saw fabricated figures presented exactly like real ones, and the
charts carried no label saying otherwise. A dashboard that invents data on a
connection error is worse than one that goes dark, because it is confidently
wrong and nothing on screen says so.

So the contract here is that every failure path returns None: no credentials, no
database, an unreadable schema, a malformed query. The app renders an explicit,
labelled offline state and displays nothing at all rather than anything made up.

`connect` is injectable so the failure paths are unit-testable without a
database. Credentials come from the same PORTFOLIO_DB_* variables the compose
stack injects.
"""

import os

import pandas as pd
import psycopg2

# The analytics layer is the app's entire read surface. Naming the queries here
# rather than inlining them in render code keeps the app's data dependencies
# greppable in one place.
#
# SECURITY: these are written out in full rather than composed from a schema
# constant, deliberately. Every query is then a literal with no interpolation of
# any kind, which is both obviously injection-free on inspection and clean under
# static analysis; an f-string here trips B608 and the suppression would be more
# noise than the duplication it saves.
QUERIES = {
    "platform_health": (
        "select * from public_ads_analytics.mart_platform_health order by full_date"
    ),
    "campaign_performance": (
        "select * from public_ads_analytics.mart_campaign_performance "
        "order by campaign_key, date_key"
    ),
    "frequency_analysis": (
        "select * from public_ads_analytics.mart_frequency_analysis"
    ),
    "advertiser_summary": (
        "select * from public_ads_analytics.mart_advertiser_summary order by total_spend desc"
    ),
    "advertiser_concentration": (
        "select * from public_ads_analytics.mart_advertiser_concentration"
    ),
}


def fetch(name: str, connect=psycopg2.connect) -> pd.DataFrame | None:
    """Run one of the named analytics queries.

    Args:
        name: a key of QUERIES.
        connect: connection factory, injected in tests.

    Returns:
        The result as a DataFrame, or None if the data could not be read for
        any reason. An empty DataFrame is a valid result and means the query
        succeeded against an empty table; None means it did not succeed.

    Raises:
        KeyError: if name is not a known query. That is a programming error in
            the app rather than an environment problem, so it is loud: failing
            quietly here would hide a typo behind the offline banner.
    """
    sql = QUERIES[name]

    password = os.getenv("PORTFOLIO_DB_PASSWORD")
    if not password:
        # no attempt at all without credentials: a standalone run stays fast
        # and silent rather than waiting on a connection that cannot succeed.
        return None

    try:
        conn = connect(
            host=os.getenv("PORTFOLIO_DB_HOST", "127.0.0.1"),
            port=os.getenv("PORTFOLIO_DB_PORT", "55434"),
            user=os.getenv("PORTFOLIO_DB_USER", "portfolio_reader"),
            password=password,
            dbname=os.getenv("PORTFOLIO_DB_NAME", "draupnir"),
            connect_timeout=3,
        )
    except psycopg2.Error:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                return None
            columns = [c[0] for c in cur.description]
            rows = cur.fetchall()
    except psycopg2.Error:
        return None
    finally:
        conn.close()

    return pd.DataFrame(rows, columns=columns)
