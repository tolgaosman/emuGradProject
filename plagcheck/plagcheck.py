""" plagcheck.py — CLI entry point. """
import argparse
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


def main():
    """Parse CLI args, run a scan over --files, and write report artifacts."""
    parser = argparse.ArgumentParser(description="Plagiarism and Similarity Detection")
    parser.add_argument("--files", nargs="+", required=True, help="List of file paths to scan")
    parser.add_argument(
        "--mode",
        choices=sorted(MODES),
        default=None,
        help="Scanning mode (default: text_similarity, or DEFAULT_MODE env var)",
    )
    parser.add_argument(
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

    args = parser.parse_args()
    mode = _resolve_mode(args)
    algorithm = _resolve_algorithm(args, mode)

    if not (0.01 <= args.threshold <= 0.99):
        print("Error: Threshold must be between 0.01 and 0.99")
        return 1

    if len(args.files) > MAX_FILES:
        print(f"Error: Batch of {len(args.files)} exceeds max of {MAX_FILES} files.")
        return 1

    scan_uuid = str(uuid.uuid4())
    audit = AuditLogger()
    audit.log("SCAN_START", scan_uuid=scan_uuid, payload={"files": args.files, "mode": mode})

    loader = FileLoader()
    preprocessor = Preprocessor(exclusions_path=args.exclusions)
    file_data = {}
    files_meta = []
    name_counts: dict[str, int] = {}

    print(f"Loading {len(args.files)} files for mode '{mode}'...")
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

    print(f"Running '{mode}' (algorithm: {algorithm})...")
    engine = ScanEngine(mode=mode, algorithm=algorithm)
    result = engine.compute(
        file_data, preprocessor=preprocessor, min_match_words=args.min_match_words
    )

    ScanRepository().save_scan(mode, args.threshold, files_meta, result, scan_uuid)

    os.makedirs(args.output, exist_ok=True)

    assert result.matrix is not None  # guaranteed by ScanEngine.compute
    reporter = ReportGenerator()
    artifacts = reporter.generate(
        result.matrix,
        args.output,
        threshold=args.threshold,
        file_data=file_data,
        preprocessor=preprocessor,
        min_match_words=args.min_match_words,
        formats=args.format,
    )
    flagged = result.matrix.get_flagged(args.threshold)
    flagged_count = len(flagged)

    print(f"\nScan complete. Flagged pairs (>= {args.threshold}):")
    if not flagged:
        print("  None")
    else:
        for f in flagged:
            print(f"  {f['file_a']} <-> {f['file_b']} : {f['score']:.4f}")

    print(f"\nArtifacts generated in '{args.output}':")
    for key in ("csv", "html", "heatmap"):
        if key in artifacts:
            print(f"  - {artifacts[key]}")

    audit.log("SCAN_COMPLETE", scan_uuid=scan_uuid, payload={"flagged_count": flagged_count})
    return 0


if __name__ == "__main__":
    # Propagate the exit code so a caller/script can tell a failed scan from
    # a successful one — main() previously always exited 0, even after
    # printing "Error: ...".
    sys.exit(main())
