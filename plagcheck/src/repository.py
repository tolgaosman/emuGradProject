""" repository.py — ScanRepository: persists scans across the 3NF schema.

Writes scan_request -> scan_file -> scan_algorithm -> scan_pair in one
transaction. When PostgreSQL is unreachable, falls back to a JSON file per
scan under `output/scans/`, mirroring the offline fallback pattern in
`audit.py`. `get_scan` reads DB-first, then the JSON fallback, so a report
stays retrievable across process restarts either way.
"""
import json
import os
import uuid
from datetime import datetime

import psycopg2

from .matrix import ComparisonMatrix

_SYSTEM_USER_EMAIL = "system@plagcheck.local"
_JSON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "output", "scans"))


class ScanRepository:
    """Persists and retrieves scan results across the six-table schema."""

    def __init__(self, json_dir: str = _JSON_DIR):
        """Read DB connection parameters from the environment."""
        self.db_host = os.environ.get("DB_HOST", "localhost")
        self.db_name = os.environ.get("DB_NAME", "plagcheck_db")
        self.db_user = os.environ.get("DB_USER", "plagcheck_user")
        self.db_pass = os.environ.get("DB_PASS", "password")
        self.db_port = os.environ.get("DB_PORT", "5432")
        self.json_dir = json_dir

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

    def save_scan(
        self,
        algorithm: str,
        threshold: float,
        files_meta: list[dict],
        matrix: ComparisonMatrix,
        scan_uuid: str | None = None,
    ) -> str:
        """Persist a completed scan and return its public scan_uuid.

        `files_meta` is `[{"file_name", "file_size_bytes", "file_format"}, ...]`
        in the same order as `matrix.names`. Falls back to a JSON file under
        `output/scans/` when PostgreSQL is unreachable.
        """
        scan_uuid = scan_uuid or str(uuid.uuid4())
        record = self._build_record(scan_uuid, algorithm, threshold, files_meta, matrix)

        conn = self._get_connection()
        if conn:
            try:
                self._save_db(conn, record)
                conn.commit()
                return scan_uuid
            except Exception:
                conn.rollback()
            finally:
                conn.close()

        self._save_json(record)
        return scan_uuid

    def get_scan(self, scan_uuid: str) -> dict | None:
        """Return a persisted scan by its public UUID, or None if not found."""
        conn = self._get_connection()
        if conn:
            try:
                record = self._load_db(conn, scan_uuid)
                if record is not None:
                    return record
            except Exception:
                pass
            finally:
                conn.close()
        return self._load_json(scan_uuid)

    # -- record construction -------------------------------------------------

    def _build_record(
        self,
        scan_uuid: str,
        algorithm: str,
        threshold: float,
        files_meta: list[dict],
        matrix: ComparisonMatrix,
    ) -> dict:
        pairs = [
            {**pair, "flagged": pair["score"] >= threshold} for pair in matrix.all_pairs()
        ]
        return {
            "scan_uuid": scan_uuid,
            "algorithm": algorithm,
            "threshold": threshold,
            "status": "complete",
            "timestamp": datetime.now().isoformat(),
            "files": files_meta,
            "pairs": pairs,
        }

    # -- PostgreSQL ------------------------------------------------------------

    def _get_or_create_system_user(self, conn) -> int:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM app_user WHERE user_email = %s", (_SYSTEM_USER_EMAIL,))
            row = cur.fetchone()
            if row:
                return row[0]
            cur.execute(
                "INSERT INTO app_user (user_name, user_email, user_role) "
                "VALUES ('system', %s, 'admin') RETURNING user_id",
                (_SYSTEM_USER_EMAIL,),
            )
            return cur.fetchone()[0]

    def _save_db(self, conn, record: dict) -> None:
        user_id = self._get_or_create_system_user(conn)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO scan_request (scan_uuid, user_id, threshold, status) "
                "VALUES (%s, %s, %s, %s) RETURNING scan_id",
                (record["scan_uuid"], user_id, record["threshold"], record["status"]),
            )
            scan_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO scan_algorithm (scan_id, algorithm_name) VALUES (%s, %s)",
                (scan_id, record["algorithm"]),
            )

            file_ids: dict[str, int] = {}
            for f in record["files"]:
                cur.execute(
                    "INSERT INTO scan_file (scan_id, file_name, file_size_bytes, file_format) "
                    "VALUES (%s, %s, %s, %s) RETURNING file_id",
                    (scan_id, f["file_name"], f["file_size_bytes"], f["file_format"]),
                )
                file_ids[f["file_name"]] = cur.fetchone()[0]

            for pair in record["pairs"]:
                id_a, id_b = file_ids[pair["file_a"]], file_ids[pair["file_b"]]
                if id_a > id_b:
                    id_a, id_b = id_b, id_a
                cur.execute(
                    "INSERT INTO scan_pair "
                    "(scan_id, file_id_a, file_id_b, similarity_score, flagged) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (scan_id, id_a, id_b, pair["score"], pair["flagged"]),
                )

    def _load_db(self, conn, scan_uuid: str) -> dict | None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT scan_id, threshold, status, scan_timestamp FROM scan_request "
                "WHERE scan_uuid = %s",
                (scan_uuid,),
            )
            row = cur.fetchone()
            if not row:
                return None
            scan_id, threshold, status, timestamp = row

            cur.execute(
                "SELECT algorithm_name FROM scan_algorithm WHERE scan_id = %s LIMIT 1", (scan_id,)
            )
            algo_row = cur.fetchone()
            algorithm = algo_row[0] if algo_row else "cosine"

            cur.execute(
                "SELECT file_id, file_name, file_size_bytes, file_format FROM scan_file "
                "WHERE scan_id = %s",
                (scan_id,),
            )
            files = {
                fid: {"file_name": name, "file_size_bytes": size, "file_format": fmt}
                for fid, name, size, fmt in cur.fetchall()
            }

            cur.execute(
                "SELECT file_id_a, file_id_b, similarity_score, flagged FROM scan_pair "
                "WHERE scan_id = %s",
                (scan_id,),
            )
            pairs = [
                {
                    "file_a": files[id_a]["file_name"],
                    "file_b": files[id_b]["file_name"],
                    "score": float(score),
                    "flagged": bool(flagged),
                }
                for id_a, id_b, score, flagged in cur.fetchall()
            ]

        return {
            "scan_uuid": scan_uuid,
            "algorithm": algorithm,
            "threshold": threshold,
            "status": status,
            "timestamp": timestamp.isoformat(),
            "files": list(files.values()),
            "pairs": pairs,
        }

    # -- JSON fallback -----------------------------------------------------

    def _json_path(self, scan_uuid: str) -> str:
        return os.path.join(self.json_dir, f"{scan_uuid}.json")

    def _save_json(self, record: dict) -> None:
        os.makedirs(self.json_dir, exist_ok=True)
        with open(self._json_path(record["scan_uuid"]), "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)

    def _load_json(self, scan_uuid: str) -> dict | None:
        path = self._json_path(scan_uuid)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
