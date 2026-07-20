# ============================================================
#  file:       app/tests/test_db.py
#  purpose:    tests that every warehouse failure path degrades to None
#  owner:      Luke Udell
#  spdx:       MIT
#  std:        [STD-02] [STD-14]
#  adr:        none
#  ticket:     none
#  ticket-url: none
#  created:    2026-07-19
# ============================================================
"""
Tests for the degradation contract.

The defect these guard against is not a crash, it is the opposite: the app used
to survive a database failure by rendering invented numbers that looked exactly
like real ones. So the assertion throughout is that a failure produces None,
never a DataFrame, because the moment a failure can return rows the offline
state stops being distinguishable from a healthy one.

Uses local fakes injected through `connect` rather than a mocking library or a
live database, so the suite stays fast and has no external dependency.
"""

import importlib.util
import pathlib

import pandas as pd
import psycopg2
import pytest

_MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent / "db.py"
_spec = importlib.util.spec_from_file_location("db", _MODULE_PATH)
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)


class _FakeCursor:
    def __init__(self, description=None, rows=None, raises=None):
        self.description = description
        self._rows = rows or []
        self._raises = raises
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        if self._raises:
            raise self._raises
        self.executed = sql

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _password(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_DB_PASSWORD", "not_a_real_password")


def _connect_returning(description, rows):
    conn = _FakeConn(_FakeCursor(description=description, rows=rows))
    return lambda **kwargs: conn


class TestHappyPath:
    def test_returns_a_dataframe_with_the_right_columns(self):
        connect = _connect_returning([("hhi",), ("concentration_band",)], [(286.1, "DIVERSIFIED")])
        out = db.fetch("advertiser_concentration", connect=connect)
        assert isinstance(out, pd.DataFrame)
        assert list(out.columns) == ["hhi", "concentration_band"]
        assert out.iloc[0]["concentration_band"] == "DIVERSIFIED"

    def test_an_empty_table_is_an_empty_frame_not_none(self):
        # an empty result means the query worked and there are no rows; that is
        # a different condition from "could not read", and must stay different
        out = db.fetch("platform_health", connect=_connect_returning([("date_key",)], []))
        assert out is not None
        assert out.empty

    def test_closes_the_connection(self):
        conn = _FakeConn(_FakeCursor(description=[("hhi",)], rows=[(1.0,)]))
        db.fetch("advertiser_concentration", connect=lambda **kw: conn)
        assert conn.closed


class TestFailurePathsReturnNone:
    def test_missing_password_returns_none_without_connecting(self, monkeypatch):
        monkeypatch.delenv("PORTFOLIO_DB_PASSWORD", raising=False)
        attempted = []

        def connect(**kwargs):
            attempted.append(kwargs)
            raise AssertionError("should not have attempted a connection")

        assert db.fetch("platform_health", connect=connect) is None
        assert attempted == []

    def test_connection_error_returns_none(self):
        def connect(**kwargs):
            raise psycopg2.OperationalError("could not connect")

        assert db.fetch("platform_health", connect=connect) is None

    def test_query_error_returns_none(self):
        cursor = _FakeCursor(raises=psycopg2.ProgrammingError("relation does not exist"))
        conn = _FakeConn(cursor)
        assert db.fetch("platform_health", connect=lambda **kw: conn) is None

    def test_query_error_still_closes_the_connection(self):
        cursor = _FakeCursor(raises=psycopg2.ProgrammingError("boom"))
        conn = _FakeConn(cursor)
        db.fetch("platform_health", connect=lambda **kw: conn)
        assert conn.closed

    def test_statement_with_no_result_set_returns_none(self):
        # description is None when the statement returned no rows at all
        conn = _FakeConn(_FakeCursor(description=None, rows=[]))
        assert db.fetch("platform_health", connect=lambda **kw: conn) is None

    @pytest.mark.parametrize("name", sorted(db.QUERIES))
    def test_every_query_degrades_the_same_way(self, name):
        def connect(**kwargs):
            raise psycopg2.OperationalError("down")

        assert db.fetch(name, connect=connect) is None


class TestQueryCatalog:
    def test_unknown_query_raises_rather_than_degrading(self):
        # a typo in the app is a bug, not an outage; hiding it behind the
        # offline banner would make it invisible
        with pytest.raises(KeyError):
            db.fetch("no_such_table", connect=lambda **kw: None)

    def test_every_query_targets_the_analytics_schema(self):
        for name, sql in db.QUERIES.items():
            assert "public_ads_analytics." in sql, name

    def test_no_query_selects_from_staging_or_marts(self):
        # the reader role is meant to read the presentation layer only
        for name, sql in db.QUERIES.items():
            assert "ads_staging" not in sql, name
            assert "public_ads_mart." not in sql, name

    def test_the_app_reads_exactly_the_models_it_needs(self):
        assert set(db.QUERIES) == {
            "platform_health",
            "campaign_performance",
            "frequency_analysis",
            "advertiser_summary",
            "advertiser_concentration",
        }
