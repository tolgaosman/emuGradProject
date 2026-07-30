""" repository.py — ScanRepository: persists scans across the 3NF schema.

Writes scan_request -> scan_file -> scan_algorithm -> scan_pair (similarity
modes) or -> scan_ai_result (AI modes) in one transaction. When PostgreSQL is
unreachable, falls back to a JSON file per scan under `output/scans/`,
mirroring the offline fallback pattern in `audit.py`. `get_scan` reads
DB-first, then the JSON fallback, so a report stays retrievable across
process restarts either way.
"""
import json
import logging
import os
import uuid
from datetime import datetime

import psycopg2

from .engine import ScanResult
from .language import MODES

_SYSTEM_USER_EMAIL = "system@plagcheck.local"
_JSON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "output", "scans"))

logger = logging.getLogger(__name__)


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
        mode: str,
        threshold: float,
        files_meta: list[dict],
        result: ScanResult,
        scan_uuid: str | None = None,
    ) -> str:
        """Persist a completed scan and return its public scan_uuid.

        `files_meta` is `[{"file_name", "file_size_bytes", "file_format"}, ...]`
        in the same order as `result.names`. Falls back to a JSON file under
        `output/scans/` when PostgreSQL is unreachable *or* when the DB
        write itself fails (e.g. a constraint violation) — that failure is
        logged loudly rather than swallowed, since a silent fallback would
        otherwise look identical to a successful relational write.
        """
        scan_uuid = scan_uuid or str(uuid.uuid4())
        record = self._build_record(scan_uuid, mode, threshold, files_meta, result)

        conn = self._get_connection()
        if conn:
            try:
                self._save_db(conn, record)
                conn.commit()
                return scan_uuid
            except Exception:
                logger.exception(
                    "DB write failed for scan %s (mode=%s) — falling back to JSON", scan_uuid, mode
                )
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
                logger.exception("DB read failed for scan %s — falling back to JSON", scan_uuid)
            finally:
                conn.close()
        return self._load_json(scan_uuid)

    # -- record construction -------------------------------------------------

    def _build_record(
        self,
        scan_uuid: str,
        mode: str,
        threshold: float,
        files_meta: list[dict],
        result: ScanResult,
    ) -> dict:
        if result.is_ai:
            pairs: list[dict] = []
            files = list(files_meta)
            ai_results = [
                {"file": name, **result.ai_assessments[name].to_dict()}
                for name in result.names
                if name in result.ai_assessments
            ]
        else:
            pairs = [
                {**pair, "flagged": pair["score"] >= threshold}
                for pair in (result.matrix.all_pairs() if result.matrix else [])
            ]
            files = [
                {**f, "similarity_index": result.similarity_indices.get(f["file_name"])}
                for f in files_meta
            ]
            ai_results = []

        web_matches = {
            name: [m.to_dict() for m in matches] for name, matches in result.web_matches.items()
        }

        return {
            "scan_uuid": scan_uuid,
            "algorithm": mode,
            "algorithm_override": result.algorithm,
            "threshold": threshold,
            "status": "complete",
            "timestamp": datetime.now().isoformat(),
            "files": files,
            "pairs": pairs,
            "ai_scores": ai_results,
            "source_breakdowns": result.source_breakdowns,
            "web_matches": web_matches,
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
            # Also record the effective per-algorithm override (e.g. "ast"
            # forced instead of the mode's default blend), when it differs
            # from the mode name itself — scan_algorithm is a composite-PK
            # table designed to hold more than one row per scan.
            override = record.get("algorithm_override", "auto")
            if override not in (record["algorithm"], None):
                cur.execute(
                    "INSERT INTO scan_algorithm (scan_id, algorithm_name) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (scan_id, override),
                )

            file_ids: dict[str, int] = {}
            for f in record["files"]:
                cur.execute(
                    "INSERT INTO scan_file "
                    "(scan_id, file_name, file_size_bytes, file_format, similarity_index) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING file_id",
                    (
                        scan_id,
                        f["file_name"],
                        f["file_size_bytes"],
                        f["file_format"],
                        f.get("similarity_index"),
                    ),
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

            for ai_result in record["ai_scores"]:
                file_id = file_ids.get(ai_result["file"])
                if file_id is None:
                    continue
                cur.execute(
                    "INSERT INTO scan_ai_result (scan_id, file_id, probability, band) "
                    "VALUES (%s, %s, %s, %s)",
                    (scan_id, file_id, ai_result["overall_probability"], ai_result["band"]),
                )

            for file_name, matches in record.get("web_matches", {}).items():
                file_id = file_ids.get(file_name)
                if file_id is None:
                    continue
                for match in matches:
                    cur.execute(
                        "INSERT INTO scan_web_match "
                        "(scan_id, file_id, query, url, title, score) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (
                            scan_id,
                            file_id,
                            match["query"],
                            match["url"],
                            match["title"],
                            match["score"],
                        ),
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
                "SELECT algorithm_name FROM scan_algorithm WHERE scan_id = %s", (scan_id,)
            )
            algo_names = [row[0] for row in cur.fetchall()]
            modes_present = [a for a in algo_names if a in MODES]
            if modes_present:
                algorithm = modes_present[0]
            elif algo_names:
                algorithm = algo_names[0]
            else:
                algorithm = "text_similarity"
            overrides = [a for a in algo_names if a != algorithm]
            algorithm_override = overrides[0] if overrides else "auto"

            cur.execute(
                "SELECT file_id, file_name, file_size_bytes, file_format, similarity_index "
                "FROM scan_file WHERE scan_id = %s",
                (scan_id,),
            )
            files = {
                fid: {
                    "file_name": name,
                    "file_size_bytes": size,
                    "file_format": fmt,
                    "similarity_index": float(index) if index is not None else None,
                }
                for fid, name, size, fmt, index in cur.fetchall()
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

            cur.execute(
                "SELECT file_id, probability, band FROM scan_ai_result WHERE scan_id = %s",
                (scan_id,),
            )
            ai_scores = [
                {
                    "file": files[file_id]["file_name"],
                    "overall_probability": float(prob),
                    "band": band,
                }
                for file_id, prob, band in cur.fetchall()
                if file_id in files
            ]

            cur.execute(
                "SELECT file_id, query, url, title, score FROM scan_web_match "
                "WHERE scan_id = %s",
                (scan_id,),
            )
            web_matches: dict[str, list[dict]] = {}
            for file_id, query, url, title, score in cur.fetchall():
                if file_id not in files:
                    continue
                web_matches.setdefault(files[file_id]["file_name"], []).append(
                    {"query": query, "url": url, "title": title, "score": float(score)}
                )

        return {
            "scan_uuid": scan_uuid,
            "algorithm": algorithm,
            "algorithm_override": algorithm_override,
            "threshold": threshold,
            "status": status,
            "timestamp": timestamp.isoformat(),
            "files": list(files.values()),
            "pairs": pairs,
            "ai_scores": ai_scores,
            # Ranked per-source contributions aren't persisted relationally
            # (see the docstring on scan_ai_result) — only available for
            # scans that are still in the JSON fallback / same-process cache.
            "source_breakdowns": {},
            "web_matches": web_matches,
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
