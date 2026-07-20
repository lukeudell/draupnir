# ============================================================
#  file:       data/load_ads_data.py
#  purpose:    loads the generated CSVs into the ads_staging schema
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-04]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Draupnir: ad platform data loader
Creates ads_staging schema in PostgreSQL and loads generated ads CSVs.
Grants portfolio_reader access on both ads_staging and dbt-created public_ads_* schemas.

Usage:
    python load_ads_data.py [--host 127.0.0.1] [--port 5432]
"""

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():  # local-dev convenience only; production injects env, no .env present
    load_dotenv(_env_path)

CSV_DIR = Path(__file__).parent / "generated" / "ads"
ADS_STAGING = "ads_staging"

STAGING_TABLES = {
    "ad_slots": """
        CREATE TABLE IF NOT EXISTS {schema}.ad_slots (
            slot_position         VARCHAR(20) PRIMARY KEY,
            typical_duration_sec  SMALLINT NOT NULL,
            avg_completion_rate   NUMERIC(5,2) NOT NULL,
            avg_viewability       NUMERIC(5,2) NOT NULL
        )
    """,
    "advertisers": """
        CREATE TABLE IF NOT EXISTS {schema}.advertisers (
            advertiser_id      VARCHAR(20) PRIMARY KEY,
            company_name       VARCHAR(200) NOT NULL,
            industry_vertical  VARCHAR(50) NOT NULL,
            spend_tier         VARCHAR(20) NOT NULL,
            country            VARCHAR(10) NOT NULL
        )
    """,
    "content_catalog": """
        CREATE TABLE IF NOT EXISTS {schema}.content_catalog (
            content_id           VARCHAR(20) PRIMARY KEY,
            title                VARCHAR(500) NOT NULL,
            content_type         VARCHAR(20) NOT NULL,
            genre                VARCHAR(50) NOT NULL,
            avg_episode_minutes  SMALLINT NOT NULL,
            maturity_rating      VARCHAR(10) NOT NULL
        )
    """,
    "subscribers": """
        CREATE TABLE IF NOT EXISTS {schema}.subscribers (
            subscriber_id       VARCHAR(20) PRIMARY KEY,
            subscription_tier   VARCHAR(20) NOT NULL,
            signup_date         DATE NOT NULL,
            region              VARCHAR(20) NOT NULL,
            device_primary      VARCHAR(20) NOT NULL,
            age_band            VARCHAR(10) NOT NULL
        )
    """,
    "campaigns": """
        CREATE TABLE IF NOT EXISTS {schema}.campaigns (
            campaign_id      VARCHAR(20) PRIMARY KEY,
            advertiser_id    VARCHAR(20) NOT NULL,
            campaign_name    VARCHAR(500) NOT NULL,
            objective        VARCHAR(20) NOT NULL,
            daily_budget_usd NUMERIC(12,2) NOT NULL,
            total_budget_usd NUMERIC(12,2) NOT NULL,
            flight_start     DATE NOT NULL,
            flight_end       DATE NOT NULL,
            flight_days      SMALLINT NOT NULL,
            frequency_cap    SMALLINT NOT NULL,
            pacing_goal      VARCHAR(20) NOT NULL,
            status           VARCHAR(20) NOT NULL
        )
    """,
    "dates_ads": """
        CREATE TABLE IF NOT EXISTS {schema}.dates_ads (
            date_key     INTEGER PRIMARY KEY,
            full_date    DATE NOT NULL,
            day_of_week  VARCHAR(10) NOT NULL,
            is_weekend   BOOLEAN NOT NULL,
            week_of_year SMALLINT NOT NULL,
            month_name   VARCHAR(10) NOT NULL,
            quarter      VARCHAR(5) NOT NULL,
            year         SMALLINT NOT NULL
        )
    """,
    "viewing_sessions": """
        CREATE TABLE IF NOT EXISTS {schema}.viewing_sessions (
            session_id     VARCHAR(20) PRIMARY KEY,
            subscriber_id  VARCHAR(20) NOT NULL,
            content_id     VARCHAR(20) NOT NULL,
            session_start  TIMESTAMP NOT NULL,
            device         VARCHAR(20) NOT NULL,
            watch_seconds  INTEGER NOT NULL,
            deepest_slot   VARCHAR(20) NOT NULL,
            ad_requests    SMALLINT NOT NULL
        )
    """,
    "ad_requests": """
        CREATE TABLE IF NOT EXISTS {schema}.ad_requests (
            request_id         VARCHAR(20) PRIMARY KEY,
            session_id         VARCHAR(20) NOT NULL,
            subscriber_id      VARCHAR(20) NOT NULL,
            content_id         VARCHAR(20) NOT NULL,
            slot_position      VARCHAR(20) NOT NULL,
            request_timestamp  TIMESTAMP NOT NULL,
            device             VARCHAR(20) NOT NULL,
            was_filled         BOOLEAN NOT NULL
        )
    """,
    "ad_impressions": """
        CREATE TABLE IF NOT EXISTS {schema}.ad_impressions (
            impression_id        VARCHAR(20) PRIMARY KEY,
            request_id           VARCHAR(20) NOT NULL,
            campaign_id          VARCHAR(20) NOT NULL,
            advertiser_id        VARCHAR(20) NOT NULL,
            subscriber_id        VARCHAR(20) NOT NULL,
            content_id           VARCHAR(20) NOT NULL,
            slot_position        VARCHAR(20) NOT NULL,
            device               VARCHAR(20) NOT NULL,
            bid_price_usd        NUMERIC(12,6) NOT NULL,
            revenue_usd          NUMERIC(12,6) NOT NULL,
            is_viewable          BOOLEAN NOT NULL,
            completed            BOOLEAN NOT NULL,
            view_duration_sec    SMALLINT NOT NULL,
            impression_timestamp TIMESTAMP NOT NULL
        )
    """,
}


def get_connection(args):
    return psycopg2.connect(
        host=args.host or os.getenv("PORTFOLIO_DB_HOST", "127.0.0.1"),
        port=args.port or os.getenv("PORTFOLIO_DB_PORT", "5432"),
        user=args.user or os.getenv("PORTFOLIO_DB_USER", "draupnir_admin"),
        password=args.password or os.getenv("PORTFOLIO_DB_PASSWORD"),
        dbname=args.dbname or os.getenv("PORTFOLIO_DB_NAME", "draupnir"),
    )


def create_schema_and_tables(conn):
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
            sql.Identifier(ADS_STAGING)
        ))
        for table_name, ddl_template in STAGING_TABLES.items():
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {}.{} CASCADE").format(
                sql.Identifier(ADS_STAGING), sql.Identifier(table_name),
            ))
            cur.execute(ddl_template.replace("{schema}", ADS_STAGING))
            print(f"  Created {ADS_STAGING}.{table_name}")
    conn.commit()


def load_csv(conn, table_name, csv_path):
    with conn.cursor() as cur:
        with open(csv_path, "r", encoding="utf-8") as f:
            cur.copy_expert(
                sql.SQL("COPY {}.{} FROM STDIN WITH (FORMAT csv, HEADER true)").format(
                    sql.Identifier(ADS_STAGING), sql.Identifier(table_name),
                ).as_string(conn),
                f,
            )
    conn.commit()


def ensure_reader_role(conn, reader_password: str):
    """
    Create the portfolio_reader login role if it is absent.

    This loader used to assume the role already existed, because something else
    happened to create it first. That made the dependency real but invisible:
    the load succeeded and then failed at the grant the moment it ran anywhere
    on its own. An assumption that only holds by running order is not an
    assumption, so it became a step.

    Idempotent: an existing role keeps its current password rather than being
    dropped, because dropping a role that owns objects fails in ways that are
    tedious to unpick mid-load.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'portfolio_reader'")
        if cur.fetchone():
            print("  portfolio_reader already exists, leaving it alone")
            return
        cur.execute(
            sql.SQL("CREATE ROLE portfolio_reader WITH LOGIN PASSWORD {}").format(
                sql.Literal(reader_password)
            )
        )
        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO portfolio_reader").format(
                sql.Identifier(conn.info.dbname)
            )
        )
    conn.commit()
    print("  Created portfolio_reader role")


def grant_reader_access(conn):
    """Grant portfolio_reader on both raw and dbt-created schemas.
    dbt prefixes with 'public_', so we grant on both naming conventions."""
    all_schemas = [
        "ads_staging",
        "ads_staging_v", "public_ads_staging_v",
        "ads_mart", "public_ads_mart",
        "ads_analytics", "public_ads_analytics",
    ]
    with conn.cursor() as cur:
        for schema in all_schemas:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                sql.Identifier(schema)
            ))
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO portfolio_reader").format(
                sql.Identifier(schema)
            ))
            cur.execute(sql.SQL(
                "GRANT SELECT ON ALL TABLES IN SCHEMA {} TO portfolio_reader"
            ).format(sql.Identifier(schema)))
            cur.execute(sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA {} "
                "GRANT SELECT ON TABLES TO portfolio_reader"
            ).format(sql.Identifier(schema)))
    conn.commit()
    print("\n  Granted portfolio_reader access to all ads schemas (including public_ prefix)")


def verify_row_counts(conn):
    print("\n--- Row Count Verification ---")
    with conn.cursor() as cur:
        for table_name in STAGING_TABLES:
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                sql.Identifier(ADS_STAGING), sql.Identifier(table_name),
            ))
            count = cur.fetchone()[0]
            print(f"  {ADS_STAGING}.{table_name}: {count:,} rows")


def main():
    parser = argparse.ArgumentParser(description="Load ads CSVs into PostgreSQL")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--dbname", default=None)
    parser.add_argument(
        "--reader-password",
        default=os.getenv("READER_DB_PASSWORD"),
        help="Password for the portfolio_reader role (or set READER_DB_PASSWORD)",
    )
    args = parser.parse_args()

    if not args.reader_password:
        parser.error("--reader-password is required (or set READER_DB_PASSWORD)")


    conn = get_connection(args)
    conn.autocommit = False

    print("Creating ads staging schema and tables...")
    create_schema_and_tables(conn)

    # why: the load list is derived from STAGING_TABLES rather than repeated.
    # It used to be a second hardcoded mapping, and the two drifted the moment a
    # table was added: viewing_sessions got its DDL and its CSV but never got a
    # load, so the table existed and stayed empty. Nothing failed, because a
    # missing CSV was a skip and an empty table is not an error. Insertion order
    # is the load order, so dimensions must stay declared before the facts that
    # reference them.
    print("\nLoading CSVs...")
    missing = []
    for table_name in STAGING_TABLES:
        csv_path = CSV_DIR / f"{table_name}.csv"
        if not csv_path.exists():
            missing.append(csv_path.name)
            continue
        load_csv(conn, table_name, csv_path)
        print(f"  Loaded {csv_path.name} -> {ADS_STAGING}.{table_name}")

    if missing:
        # loudly, and before the grants: a partial load that looks successful is
        # how a downstream model ends up silently reading an empty table.
        raise SystemExit(
            "ERROR: no CSV found for: " + ", ".join(missing)
            + "\nRun generate_ads_data.py first."
        )

    verify_row_counts(conn)

    print("\nGranting reader access...")
    ensure_reader_role(conn, args.reader_password)
    grant_reader_access(conn)

    conn.close()
    print("\nAds data load complete.")


if __name__ == "__main__":
    main()
