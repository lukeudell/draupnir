#!/usr/bin/env bash
# ============================================================
#  file:       data/seed.sh
#  purpose:    one-shot seed: generate, load, then hand off to dbt build
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-04]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
set -euo pipefail

# draupnir: generate synthetic data and load it.
# Fails fast on missing configuration rather than loading a half-empty database.

missing=()
for var in PORTFOLIO_DB_HOST PORTFOLIO_DB_PORT PORTFOLIO_DB_USER PORTFOLIO_DB_PASSWORD PORTFOLIO_DB_NAME READER_DB_PASSWORD; do
    if [ -z "${!var:-}" ]; then missing+=("$var"); fi
done
if [ ${#missing[@]} -gt 0 ]; then
    echo "ERROR: missing required environment variables:"
    printf '  - %s\n' "${missing[@]}"
    echo "Check your .env against .env.example"
    exit 1
fi

DB_ARGS="--host $PORTFOLIO_DB_HOST --port $PORTFOLIO_DB_PORT --user $PORTFOLIO_DB_USER --password $PORTFOLIO_DB_PASSWORD --dbname $PORTFOLIO_DB_NAME"

echo ">>> 1/2 generating synthetic data"
python generate_ads_data.py \
    --subscribers 10000 --advertisers 100 --campaigns 500 --content 2000 \
    --requests 100000 --fill-rate 0.82

echo ">>> 2/2 loading into PostgreSQL"
python load_ads_data.py $DB_ARGS \
    --reader-password "$READER_DB_PASSWORD"

echo ""
echo "=== seeding complete ==="
echo "NOTE: run 'docker compose --profile seed run --rm dbt' next, THEN"
echo "      'python data/grant_reader_access.py' -- grants must follow dbt,"
echo "      or they silently no-op against schemas that do not exist yet."
