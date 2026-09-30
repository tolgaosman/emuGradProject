""" plagcheck.py — CLI entry point. """
import argparse
import glob
import logging
import os
import sys
import uuid

from dotenv import load_dotenv

from src.audit import AuditLogger
from src.engine import ALGORITHMS_BY_MODE, ScanEngine
from src.language import MODES, language_for_extension
from src.loader import MAX_FILES, FileLoader
from src.preprocessor import Preprocessor
from src.reporter import ReportGenerator
from src.repository import ScanRepository
from src.similarity_index import DEFAULT_MIN_MATCH_WORDS

load_dotenv()

VERSION = "1.1.0"

#: `--algorithm` is documented in the graduation report alongside `--mode`.
#: Each value both selects the mode it belongs to (AST only makes sense for
#: code; the rest default to text) *and* forces that single model, matching
#: the API's `algorithm` parameter. `all` is a legacy spelling of "the mode's
#: default", i.e. `auto` — which scores by matched-span coverage rather than
#: running any single model (see `engine.py`).
_ALGORITHM_TO_MODE = {
    "ast": "code_similarity",
    "winnowing": "text_similarity",
    "cosine": "text_similarity",
    "jaccard": "text_similarity",
    "all": "text_similarity",
}


def _resolve_mode(args) -> str:
    """Resolve the effective mode from --mode / --algorithm / the env default."""
    if args.mode:
        return args.mode
    if args.algorithm:
        mode = _ALGORITHM_TO_MODE[args.algorithm]
        print(f"Note: --algorithm also selects mode '{mode}'.")
        return mode
    return os.environ.get("DEFAULT_MODE", "text_similarity")


def _resolve_algorithm(args, mode: str) -> str:
    """Resolve which single algorithm to force, or 'auto' for the default.

    Silently degrades to `auto` when the requested algorithm isn't valid for
    the resolved mode (e.g. `--mode text_similarity --algorithm ast`), rather
    than running AST on prose and reporting a misleading 0.0.
    """
    if not args.algorithm or args.algorithm == "all":
        return "auto"
    if args.algorithm not in ALGORITHMS_BY_MODE.get(mode, []):
        print(
            f"Note: algorithm '{args.algorithm}' is not available for mode "
            f"'{mode}'; using the mode default instead."
        )
        return "auto"
    return args.algorithm


class _NullAudit:
    """Stand-in for `AuditLogger` under `--no-log`."""

    def log(self, *_args, **_kwargs) -> None:
        return None


def _expand_paths(patterns: list[str]) -> list[str]:
    """Expand wildcards ourselves: Windows shells pass `*.py` through literally.

    A pattern that matches nothing is kept as-is, so the loader reports it as
    a missing file instead of it vanishing silently.
    """
    paths: list[str] = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern)) if glob.has_magic(pattern) else []
        paths.extend(matches or [pattern])
    return paths


def main():
    """Parse CLI args, run a scan over --files, and write report artifacts."""
    parser = argparse.ArgumentParser(
        prog="plagcheck", description="Plagiarism and Similarity Detection (offline)"
    )
    parser.add_argument(
        "-f",
        "--files",
        nargs="+",
        required=True,
        help="Files to scan; wildcards such as docs/*.pdf are expanded",
    )
    parser.add_argument(
        "--mode",
        choices=sorted(MODES),
        default=None,
        help="Scanning mode (default: text_similarity, or DEFAULT_MODE env var)",
    )
    parser.add_argument(
        "-a",
        "--algorithm",
        choices=sorted(_ALGORITHM_TO_MODE),
        default=None,
        help="Force a single algorithm (and, unless --mode is given, its mode)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=float(os.environ.get("DEFAULT_THRESHOLD", "0.70")),
        help="Similarity threshold (0.01 - 0.99)",
    )
    parser.add_argument(
        "--output", type=str, default="output", help="Output directory for reports"
    )
    parser.add_argument(
        "--format", choices=["html", "csv", "both"], default="both", help="Report format"
    )
    parser.add_argument(
        "--exclusions",
        type=str,
        default=None,
        help="Path to an academic exclusion list (default: config/exclusions.txt)",
    )
    parser.add_argument(
        "--min-match-words",
        type=int,
        default=DEFAULT_MIN_MATCH_WORDS,
        help=(
            "Ignore matches shorter than this many words "
            f"(default: {DEFAULT_MIN_MATCH_WORDS}, 0 disables)"
        ),
    )

    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Only print errors and flagged pairs"
    )
    parser.add_argument(
        "--no-log", action="store_true", help="Do not write audit events for this run"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO)
    say = (lambda *_a, **_k: None) if args.quiet else print
    args.files = _expand_paths(args.files)
    mode = _resolve_mode(args)
    algorithm = _resolve_algorithm(args, mode)

    if not (0.01 <= args.threshold <= 0.99):
        print("Error: Threshold must be between 0.01 and 0.99")
        return 1

    if len(args.files) > MAX_FILES:
        print(f"Error: Batch of {len(args.files)} exceeds max of {MAX_FILES} files.")
        return 1

    scan_uuid = str(uuid.uuid4())
    audit = _NullAudit() if args.no_log else AuditLogger()
    audit.log(
        "SCAN_START",
        scan_uuid=scan_uuid,
        payload={
            "files": [os.path.basename(f) for f in args.files],
            "mode": mode,
            "algorithm": algorithm,
            "threshold": args.threshold,
        },
    )

    loader = FileLoader()
    preprocessor = Preprocessor(exclusions_path=args.exclusions)
    file_data = {}
    files_meta = []
    name_counts: dict[str, int] = {}

    say(f"Loading {len(args.files)} files for mode '{mode}'...")
    for raw_path in args.files:
        # Resolve to an absolute path first. The loader rejects '..' as a path
        # component to stop traversal from untrusted API input, but a CLI
        # operator legitimately passes relative paths like ../samples/a.txt,
        # and they already have shell-level filesystem access anyway.
        path = os.path.abspath(raw_path)
        try:
            raw_text = loader.load(path, mode=mode)
            ext = os.path.splitext(path)[1].lower()
            language = language_for_extension(ext) or "text"
            tokens, kgrams = preprocessor.process(raw_text, language=language)

            # Two paths can share a basename (`old/report.txt`,
            # `new/report.txt`); without this they'd overwrite each other in
            # file_data and silently collapse the batch. Mirrors the same
            # disambiguation `app.py` does for duplicate uploads.
            base = os.path.basename(path)
            occurrence = name_counts.get(base, 0)
            name_counts[base] = occurrence + 1
            if occurrence:
                stem, dupe_ext = os.path.splitext(base)
                name = f"{stem} ({occurrence + 1}){dupe_ext}"
            else:
                name = base

            file_data[name] = {
                "raw": raw_text,
                "tokens": tokens,
                "kgrams": kgrams,
                "language": language,
            }
            files_meta.append({
                "file_name": name,
                "file_size_bytes": os.path.getsize(path),
                "file_format": ext.lstrip(".").lower(),
            })
        except Exception as e:
            print(f"Skipping {path}: {e}")
            audit.log("FILE_REJECTED", scan_uuid=scan_uuid, payload={"file": path, "error": str(e)})

    # A single valid file is enough (it just has no pairs, an empty flagged
    # list, and no similarity index contributors).
    if not file_data:
        print(f"Error: Need at least 1 valid file for mode '{mode}'.")
        return 1

    say(f"Running '{mode}' (algorithm: {algorithm})...")
    engine = ScanEngine(mode=mode, algorithm=algorithm)
    result = engine.compute(
        file_data, preprocessor=preprocessor, min_match_words=args.min_match_words
    )

    ScanRepository().save_scan(
        mode, args.threshold, files_meta, result, scan_uuid, min_match_words=args.min_match_words
    )
    pairs = result.pairs(args.threshold)

    os.makedirs(args.output, exist_ok=True)

    if result.matrix is None:
        print("Error: the scan produced no similarity matrix.")
        return 1
    reporter = ReportGenerator()
    artifacts = reporter.generate(
        result.matrix,
        args.output,
        threshold=args.threshold,
        file_data=file_data,
        preprocessor=preprocessor,
        min_match_words=args.min_match_words,
        formats=args.format,
        pairs=pairs,
        algorithm=algorithm,
    )
    flagged = [p for p in pairs if p["flagged"]]

    print(f"\nScan complete. Flagged for review (>= {args.threshold}):")
    if not flagged:
        print("  None")
    for p in flagged:
        print(
            f"  {p['file_a']} <-> {p['file_b']}  ({p['matched_kgrams']} matched 5-grams)"
            f" : {p['score']:.4f}"
        )

    say(f"\nArtifacts generated in '{args.output}':")
    for key in ("csv", "html", "heatmap"):
        if key in artifacts:
            say(f"  - {artifacts[key]}")

    audit.log(
        "SCAN_COMPLETE",
        scan_uuid=scan_uuid,
        payload={
            "files": list(file_data),
            "mode": mode,
            "algorithm": algorithm,
            "threshold": args.threshold,
            "max_score": max((p["score"] for p in pairs), default=0.0),
            "flagged_count": len(flagged),
        },
    )
    return 0


if __name__ == "__main__":
    # Propagate the exit code so a caller/script can tell a failed scan from
    # a successful one — main() previously always exited 0, even after
    # printing "Error: ...".
    sys.exit(main())
