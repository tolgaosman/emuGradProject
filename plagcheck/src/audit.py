""" audit.py — AuditLogger. """
import os
import json
import psycopg2
from datetime import datetime

class AuditLogger:
    def __init__(self):
        self.db_host = os.environ.get("DB_HOST", "localhost")
        self.db_name = os.environ.get("DB_NAME", "plagcheck_db")
        self.db_user = os.environ.get("DB_USER", "plagcheck_user")
        self.db_pass = os.environ.get("DB_PASS", "password")
        self.db_port = os.environ.get("DB_PORT", "5432")

    def _get_connection(self):
        try:
            return psycopg2.connect(
                host=self.db_host,
                database=self.db_name,
                user=self.db_user,
                password=self.db_pass,
                port=self.db_port
            )
        except Exception:
            return None

    def log(self, event_type: str, scan_id: int = None, user_id: int = None, payload: dict = None):
        detail = json.dumps(payload) if payload else None
        conn = self._get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO audit_log (scan_id, user_id, event_type, event_detail) VALUES (%s, %s, %s, %s)",
                        (scan_id, user_id, event_type, detail)
                    )
                conn.commit()
            except Exception as e:
                self._fallback_log(event_type, scan_id, user_id, payload, str(e))
            finally:
                conn.close()
        else:
            self._fallback_log(event_type, scan_id, user_id, payload, "DB Connection Failed")

    def _fallback_log(self, event_type: str, scan_id: int, user_id: int, payload: dict, error_msg: str):
        with open("plagcheck.log", "a", encoding="utf-8") as f:
            ts = datetime.now().isoformat()
            log_line = f"[{ts}] {event_type} | Scan: {scan_id} | User: {user_id} | Payload: {json.dumps(payload)} | Error: {error_msg}\n"
            f.write(log_line)
