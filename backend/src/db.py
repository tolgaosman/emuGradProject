""" db.py — Shared PostgreSQL connection settings. """
import os
import time

import psycopg2

#: Short on purpose: when PostgreSQL isn't running, every caller falls back to
#: local JSON/log files, and should do so without stalling the request.
CONNECT_TIMEOUT_S = 2
#: After a failed attempt, report the database as down without retrying for
#: this long. A single scan touches the database 4+ times (audit events, the
#: record, the listing); on Windows each refused localhost connection costs
#: the full timeout, so without this an offline scan paid ~8 s in waiting.
RETRY_AFTER_S = 30.0

_down_until = 0.0


def connect():
    """Open a connection from the DB_* environment, or return None if unreachable."""
    global _down_until
    if time.monotonic() < _down_until:
        return None
    try:
        return psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            database=os.environ.get("DB_NAME", "plagcheck_db"),
            user=os.environ.get("DB_USER", "plagcheck_user"),
            password=os.environ.get("DB_PASS", ""),
            port=os.environ.get("DB_PORT", "5432"),
            connect_timeout=CONNECT_TIMEOUT_S,
        )
    except psycopg2.Error:
        _down_until = time.monotonic() + RETRY_AFTER_S
        return None
