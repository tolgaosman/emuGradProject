""" audit.py — AuditLogger. """
import json
import os
from datetime import datetime

import psycopg2


class AuditLogger:
    """Writes audit events to `audit_log`.

    Falls back to a local log file when PostgreSQL is unreachable.
    """

    def __init__(self):
        """Read DB connection parameters from the environment."""
        self.db_host = os.environ.get("DB_HOST", "localhost")
        self.db_name = os.environ.get("DB_NAME", "plagcheck_db")
        self.db_user = os.environ.get("DB_USER", "plagcheck_user")
        self.db_pass = os.environ.get("DB_PASS", "password")
        self.db_port = os.environ.get("DB_PORT", "5432")

    def _get_connection(self):
        """Return a new DB connection, or None if the DB is unreachable."""
        try:
            return psycopg2.connect(
                host=self.db_host,
                database=self.db_name,
                user=self.db_user,
                password=self.db_pass,
                port=self.db_port,
                connect_timeout=2,
            )
        except Exception:
            return None

    def log(
        self,
        event_type: str,
        scan_uuid: str | None = None,
        user_id: int | None = None,
        payload: dict | None = None,
    ) -> None:
        """Insert an audit_log row, or append to plagcheck.log if DB is down.

        `scan_uuid` is the public scan identifier (see `ScanRepository`); it
        is resolved to the internal `scan_request.scan_id` FK when a matching
        row already exists (e.g. on SCAN_COMPLETE), and left NULL otherwise
        (e.g. on SCAN_START, fired before the scan is persisted) — the raw
        UUID is always preserved in `payload` for traceability either way.
        """
        detail = json.dumps({**(payload or {}), "scan_uuid": scan_uuid})
        conn = self._get_connection()
        if not conn:
            self._fallback_log(event_type, scan_uuid, user_id, payload, "DB Connection Failed")
            return
        try:
            scan_id = self._resolve_scan_id(conn, scan_uuid)
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO audit_log (scan_id, user_id, event_type, event_detail) "
                    "VALUES (%s, %s, %s, %s)",
                    (scan_id, user_id, event_type, detail),
                )
            conn.commit()
        except Exception as e:
            self._fallback_log(event_type, scan_uuid, user_id, payload, str(e))
        finally:
            conn.close()

    def _resolve_scan_id(self, conn, scan_uuid: str | None) -> int | None:
        """Look up the internal scan_id for a public scan_uuid, if it exists."""
        if not scan_uuid:
            return None
        with conn.cursor() as cur:
            cur.execute("SELECT scan_id FROM scan_request WHERE scan_uuid = %s", (scan_uuid,))
            row = cur.fetchone()
            return row[0] if row else None

    def _fallback_log(
        self,
        event_type: str,
        scan_uuid: str | None,
        user_id: int | None,
        payload: dict | None,
        error_msg: str,
    ) -> None:
        """Append a single line to plagcheck.log when the DB write failed."""
        log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "plagcheck.log"))
        with open(log_path, "a", encoding="utf-8") as f:
            ts = datetime.now().isoformat()
            log_line = (
                f"[{ts}] {event_type} | Scan: {scan_uuid} | User: {user_id} | "
                f"Payload: {json.dumps(payload)} | Error: {error_msg}\n"
            )
            f.write(log_line)
