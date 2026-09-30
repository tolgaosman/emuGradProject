""" audit.py — AuditLogger. """
import json
import logging
import os
from datetime import UTC, datetime

from . import db

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "plagcheck.log")
)


class AuditLogger:
    """Writes audit events to `audit_log`.

    Falls back to a local log file when PostgreSQL is unreachable. Payloads
    carry scan metadata (file names, mode, algorithm, scores — FR-14), never
    document content.
    """

    def __init__(self, log_path: str = _DEFAULT_LOG_PATH):
        """Set where fallback events are appended when the DB is unavailable."""
        self.log_path = log_path

    def _get_connection(self):
        """Return a new DB connection, or None if the DB is unreachable."""
        return db.connect()

    def log(
        self,
        event_type: str,
        scan_uuid: str | None = None,
        user_id: int | None = None,
        payload: dict | None = None,
    ) -> None:
        """Insert an audit_log row, or append to the fallback log if DB is down.

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
        """Append one UTC-stamped line to the fallback log.

        Auditing must never fail the scan it describes, so a failure to write
        here (read-only disk, locked file) is logged and swallowed.
        """
        ts = datetime.now(UTC).isoformat()
        line = (
            f"[{ts}] {event_type} | Scan: {scan_uuid} | User: {user_id} | "
            f"Payload: {json.dumps(payload)} | Error: {error_msg}\n"
        )
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            logger.exception("Could not write audit fallback log %s", self.log_path)
