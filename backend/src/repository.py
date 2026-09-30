""" repository.py — ScanRepository: persists scans across the 3NF schema.

Writes scan_request -> scan_file -> scan_algorithm -> scan_pair in one
transaction. When PostgreSQL is unreachable, falls back to a JSON file per
scan under `output/scans/`, mirroring the offline fallback pattern in
`audit.py`. `get_scan` reads DB-first, then the JSON fallback, so a report
stays retrievable across process restarts either way.

Raw document text is kept apart from the record, in a `<uuid>_texts.json`
sidecar next to the JSON records: it is working data for the comparison
view, not a durable relational fact. Both expire after `RETENTION_DAYS`
(report §3.3.4: metadata is kept for 90 days, then purged).
"""
import glob
import json
import logging
import os
import time
import uuid
from datetime import datetime

from . import db
from .engine import ScanResult
from .language import MODES

_SYSTEM_USER_EMAIL = "system@plagcheck.local"
_JSON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "output", "scans"))
_TEXTS_SUFFIX = "_texts.json"
#: How long a `storage_backend()` probe is trusted. The UI polls status every
#: few seconds; without this each poll would open (or time out) a DB socket.
_STORAGE_PROBE_TTL_S = 30.0

DEFAULT_RETENTION_DAYS = 90

logger = logging.getLogger(__name__)


def is_scan_uuid(value: str) -> bool:
    """Whether `value` is a canonical UUID string (the only valid scan id)."""
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def _timestamp_key(value: str | None) -> float:
    """Sortable epoch seconds for a stored ISO timestamp (naive = local time)."""
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).astimezone().timestamp()
    except ValueError:
        return 0.0


class ScanRepository:
    """Persists and retrieves scan results across the relational schema."""

    def __init__(self, json_dir: str = _JSON_DIR):
        """Set the JSON fallback directory (records and raw-text sidecars)."""
        self.json_dir = json_dir
        self._storage_probe: tuple[float, str] | None = None

    def _get_connection(self):
        """Return a new DB connection, or None if the DB is unreachable."""
        return db.connect()

    def storage_backend(self) -> str:
        """Report where new scans are persisted: `postgres` or `json`."""
        now = time.monotonic()
        if self._storage_probe and now - self._storage_probe[0] < _STORAGE_PROBE_TTL_S:
            return self._storage_probe[1]
        conn = self._get_connection()
        backend = "postgres" if conn else "json"
        if conn:
            conn.close()
        self._storage_probe = (now, backend)
        return backend

    def save_scan(
        self,
        mode: str,
        threshold: float,
        files_meta: list[dict],
        result: ScanResult,
        scan_uuid: str | None = None,
        min_match_words: int | None = None,
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
        record = self._build_record(
            scan_uuid, mode, threshold, files_meta, result, min_match_words
        )

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

    def list_scans(self, limit: int = 20) -> list[dict]:
        """Summaries of the most recent scans, newest first, across DB and JSON.

        Expired scans are purged first, so history never offers a report whose
        comparison text is already gone.
        """
        self.purge_expired()
        summaries: dict[str, dict] = {}
        conn = self._get_connection()
        if conn:
            try:
                for summary in self._list_db(conn, limit):
                    summaries[summary["scan_uuid"]] = summary
            except Exception:
                logger.exception("DB scan listing failed — using JSON records only")
            finally:
                conn.close()
        for summary in self._list_json(limit):
            summaries.setdefault(summary["scan_uuid"], summary)
        ordered = sorted(
            summaries.values(), key=lambda s: _timestamp_key(s["timestamp"]), reverse=True
        )
        return ordered[:limit]

    def delete_scan(self, scan_uuid: str) -> bool:
        """Delete a scan's record and raw text everywhere; True if anything existed."""
        if not is_scan_uuid(scan_uuid):
            return False
        deleted = False
        conn = self._get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM scan_request WHERE scan_uuid = %s", (scan_uuid,))
                    deleted = cur.rowcount > 0
                conn.commit()
            except Exception:
                logger.exception("DB delete failed for scan %s", scan_uuid)
                conn.rollback()
            finally:
                conn.close()
        for path in (self._json_path(scan_uuid), self._texts_path(scan_uuid)):
            if os.path.isfile(path):
                os.remove(path)
                deleted = True
        return deleted

    def purge_expired(self, days: int | None = None) -> int:
        """Delete scans older than the retention window; return how many files went.

        `days` defaults to the `RETENTION_DAYS` environment variable (90).
        JSON records and sidecars are aged by file modification time.
        """
        if days is None:
            try:
                days = int(os.environ.get("RETENTION_DAYS", DEFAULT_RETENTION_DAYS))
            except ValueError:
                days = DEFAULT_RETENTION_DAYS
        cutoff = time.time() - days * 86_400

        conn = self._get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM scan_request "
                        "WHERE scan_timestamp < NOW() - make_interval(days => %s)",
                        (days,),
                    )
                conn.commit()
            except Exception:
                logger.exception("DB retention purge failed")
                conn.rollback()
            finally:
                conn.close()

        removed = 0
        for path in glob.glob(os.path.join(self.json_dir, "*.json")):
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                logger.warning("Could not purge expired scan file %s", path, exc_info=True)
        return removed

    def save_texts(self, scan_uuid: str, texts: dict, min_match_words: int) -> None:
        """Persist raw text + language per file, for the pair-comparison view.

        `texts` is `{name: {"raw": str, "language": str}}`. The scan's
        `min_match_words` rides along so the pair view can filter spans
        exactly as the scan scored them.
        """
        os.makedirs(self.json_dir, exist_ok=True)
        payload = {"min_match_words": min_match_words, "files": texts}
        with open(self._texts_path(scan_uuid), "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def load_texts(self, scan_uuid: str) -> tuple[dict, int] | None:
        """Return `(texts_by_name, min_match_words)`, or None if unavailable.

        A truncated or unreadable sidecar means the comparison simply isn't
        available — not a fault worth raising.
        """
        if not is_scan_uuid(scan_uuid):
            return None
        path = self._texts_path(scan_uuid)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        return payload.get("files", {}), int(payload.get("min_match_words", 0))

    # -- record construction -------------------------------------------------

    def _build_record(
        self,
        scan_uuid: str,
        mode: str,
        threshold: float,
        files_meta: list[dict],
        result: ScanResult,
        min_match_words: int | None = None,
    ) -> dict:
        files = [
            {**f, "similarity_index": result.similarity_indices.get(f["file_name"])}
            for f in files_meta
        ]
        return {
            "scan_uuid": scan_uuid,
            # `algorithm` historically holds the mode; `mode` says so plainly.
            "algorithm": mode,
            "mode": mode,
            "algorithm_override": result.algorithm,
            "threshold": threshold,
            "min_match_words": min_match_words,
            "status": "complete",
            "timestamp": datetime.now().astimezone().isoformat(),
            "files": files,
            "pairs": result.pairs(threshold),
            "source_breakdowns": result.source_breakdowns,
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

    def _list_db(self, conn, limit: int) -> list[dict]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT r.scan_uuid::text, r.scan_timestamp, r.threshold, "
                "(SELECT array_agg(f.file_name ORDER BY f.file_id) FROM scan_file f "
                " WHERE f.scan_id = r.scan_id), "
                "(SELECT MAX(p.similarity_score) FROM scan_pair p WHERE p.scan_id = r.scan_id), "
                "(SELECT COUNT(*) FROM scan_pair p WHERE p.scan_id = r.scan_id AND p.flagged), "
                "(SELECT a.algorithm_name FROM scan_algorithm a WHERE a.scan_id = r.scan_id "
                " AND a.algorithm_name = ANY(%s) LIMIT 1) "
                "FROM scan_request r ORDER BY r.scan_timestamp DESC LIMIT %s",
                (sorted(MODES), limit),
            )
            rows = cur.fetchall()
        return [
            {
                "scan_uuid": scan_uuid,
                "timestamp": timestamp.isoformat(),
                "mode": mode or "text_similarity",
                "threshold": threshold,
                "file_names": list(names or []),
                "max_score": float(max_score) if max_score is not None else None,
                "flagged_count": int(flagged),
            }
            for scan_uuid, timestamp, threshold, names, max_score, flagged, mode in rows
        ]

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

        return {
            "scan_uuid": scan_uuid,
            "algorithm": algorithm,
            "mode": algorithm,
            "algorithm_override": algorithm_override,
            "threshold": threshold,
            "status": status,
            "timestamp": timestamp.isoformat(),
            "files": list(files.values()),
            "pairs": pairs,
            # Ranked per-source contributions aren't persisted relationally
            # — only available for scans that are still in the JSON
            # fallback / same-process cache.
            "source_breakdowns": {},
        }

    # -- JSON fallback -----------------------------------------------------

    def _json_path(self, scan_uuid: str) -> str:
        return os.path.join(self.json_dir, f"{scan_uuid}.json")

    def _texts_path(self, scan_uuid: str) -> str:
        return os.path.join(self.json_dir, f"{scan_uuid}{_TEXTS_SUFFIX}")

    def _save_json(self, record: dict) -> None:
        os.makedirs(self.json_dir, exist_ok=True)
        with open(self._json_path(record["scan_uuid"]), "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)

    def _load_json(self, scan_uuid: str) -> dict | None:
        # Only a canonical UUID may become a filename: anything else (a
        # backslash, a drive letter, '..') could otherwise escape json_dir.
        if not is_scan_uuid(scan_uuid):
            return None
        path = self._json_path(scan_uuid)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.warning("Unreadable scan record %s", path, exc_info=True)
            return None

    def _list_json(self, limit: int) -> list[dict]:
        paths = [
            p
            for p in glob.glob(os.path.join(self.json_dir, "*.json"))
            if not p.endswith(_TEXTS_SUFFIX)
        ]
        paths.sort(key=os.path.getmtime, reverse=True)
        summaries = []
        for path in paths[:limit]:
            scan_uuid = os.path.splitext(os.path.basename(path))[0]
            record = self._load_json(scan_uuid)
            if record is not None:
                summaries.append(_summarize(record))
        return summaries


def _summarize(record: dict) -> dict:
    """Condense a full scan record into a history-list entry."""
    pairs = record.get("pairs", [])
    return {
        "scan_uuid": record["scan_uuid"],
        "timestamp": record.get("timestamp"),
        "mode": record.get("mode") or record.get("algorithm"),
        "threshold": record.get("threshold"),
        "file_names": [f["file_name"] for f in record.get("files", [])],
        "max_score": max((p["score"] for p in pairs), default=None),
        "flagged_count": sum(1 for p in pairs if p.get("flagged")),
    }
