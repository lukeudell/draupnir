# ============================================================
#  file:       data/grant_reader_access.py
#  purpose:    grants the read-only role SELECT on dbt-created schemas, after build
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-05]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Draupnir: post-dbt permission grant
Grants portfolio_reader SELECT on all dbt-created schemas.

Must be run AFTER dbt build completes, because dbt creates schemas with
a 'public_' prefix (e.g. public_ads_mart) that do not exist until dbt
materializes models. Granting first is a silent no-op, and shows up later as
"permission denied for schema" when the app connects.

Usage:
    python grant_reader_access.py [--host HOST] [--port PORT]
"""

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():  # local-dev convenience only; production injects env, no .env present
    load_dotenv(_env_path)

# All schemas that portfolio_reader should have SELECT on
DBT_SCHEMAS = [
    "public_ads_mart",
    "public_ads_analytics",
    "public_ads_staging_v",
]


def main():
    parser = argparse.ArgumentParser(description="Grant portfolio_reader on dbt schemas")
    parser.add_argument("--host", default=os.getenv("PORTFOLIO_DB_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=os.getenv("PORTFOLIO_DB_PORT", "5432"))
    parser.add_argument("--user", default=os.getenv("PORTFOLIO_DB_USER", "draupnir_admin"))
    parser.add_argument("--password", default=os.getenv("PORTFOLIO_DB_PASSWORD", ""))
    parser.add_argument("--dbname", default=os.getenv("PORTFOLIO_DB_NAME", "draupnir"))
    args = parser.parse_args()

    conn = psycopg2.connect(
        host=args.host, port=args.port,
        user=args.user, password=args.password,
        dbname=args.dbname
    )
    conn.autocommit = True
    cur = conn.cursor()

    print("Granting portfolio_reader access on dbt schemas...")
    for schema in DBT_SCHEMAS:
        # Check if schema exists
        cur.execute(
            "SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,)
        )
        if not cur.fetchone():
            print(f"  SKIP {schema} (does not exist)")
            continue

        cur.execute(f"GRANT USAGE ON SCHEMA {schema} TO portfolio_reader")
        cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO portfolio_reader")
        cur.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f"GRANT SELECT ON TABLES TO portfolio_reader"
        )
        # Count accessible tables
        cur.execute(
            "SELECT COUNT(*) FROM pg_tables WHERE schemaname = %s", (schema,)
        )
        count = cur.fetchone()[0]
        print(f"  OK {schema} ({count} tables)")

    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
