""" test_db.py — shared connection helper and its offline circuit breaker. """
import psycopg2
import pytest

from src import db


@pytest.fixture(autouse=True)
def reset_breaker(monkeypatch):
    monkeypatch.setattr(db, "_down_until", 0.0)


def test_connect_returns_connection(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(db.psycopg2, "connect", lambda **_kwargs: sentinel)
    assert db.connect() is sentinel


def test_failed_connect_opens_breaker(monkeypatch):
    calls = []

    def refuse(**_kwargs):
        calls.append(1)
        raise psycopg2.OperationalError("refused")

    monkeypatch.setattr(db.psycopg2, "connect", refuse)
    assert db.connect() is None
    assert db.connect() is None
    assert len(calls) == 1  # the second call short-circuits


def test_breaker_closes_after_retry_window(monkeypatch):
    monkeypatch.setattr(db.psycopg2, "connect", lambda **_kwargs: "conn")
    monkeypatch.setattr(db, "_down_until", db.time.monotonic() - 1)
    assert db.connect() == "conn"
