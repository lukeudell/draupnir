-- ============================================================
--  file:       data/grant_ads_access.sql
--  purpose:    grants the read-only role SELECT on the ads dbt schemas
--  owner:      Luke Udell
--  spdx:       MIT
--  std:        [STD-05]
--  adr:        none
--  ticket:     none
--  ticket-url: none
--  created:    2026-07-19
-- ============================================================
-- Covers both naming conventions. dbt prefixes its target schema onto the
-- configured one, so the same layer can appear as ads_mart or public_ads_mart
-- depending on the profile; granting on both keeps the reader role working
-- either way.

GRANT USAGE ON SCHEMA public_ads_mart TO portfolio_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public_ads_mart TO portfolio_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public_ads_mart GRANT SELECT ON TABLES TO portfolio_reader;

GRANT USAGE ON SCHEMA public_ads_analytics TO portfolio_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public_ads_analytics TO portfolio_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public_ads_analytics GRANT SELECT ON TABLES TO portfolio_reader;

GRANT USAGE ON SCHEMA public_ads_staging_v TO portfolio_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public_ads_staging_v TO portfolio_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public_ads_staging_v GRANT SELECT ON TABLES TO portfolio_reader;

-- Also grant on unprefixed schemas if they exist
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'ads_mart') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA ads_mart TO portfolio_reader';
    EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA ads_mart TO portfolio_reader';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'ads_analytics') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA ads_analytics TO portfolio_reader';
    EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA ads_analytics TO portfolio_reader';
  END IF;
END $$;
