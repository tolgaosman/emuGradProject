""" plagcheck.py — CLI entry point. """
import argparse
import json
import os
import uuid

from dotenv import load_dotenv
from src.audit import AuditLogger
from src.engine import WEB_ELIGIBLE_MODES, ScanEngine
from src.language import MODES, language_for_extension
from src.loader import MAX_FILES, FileLoader
from src.preprocessor import Preprocessor
from src.reporter import ReportGenerator
from src.repository import ScanRepository
from src.websearch import WebSearchClient

load_dotenv()

#: `--algorithm` is a legacy alias, documented in the graduation report
#: alongside `--mode`. It maps onto the mode whose composition includes that
#: algorithm most directly (AST only makes sense for code; the rest default
#: to text) — see `engine.py`'s `_CODE_*_WEIGHT` / `_TEXT_*_WEIGHT` for what
#: each mode actually composes.
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
        print(f"Note: --algorithm is a legacy alias; '{args.algorithm}' maps to mode '{mode}'.")
        return mode
    return os.environ.get("DEFAULT_MODE", "text_similarity")


def main():
    """Parse CLI args, run a scan over --files, and write report artifacts."""
    parser = argparse.ArgumentParser(description="Plagiarism, Similarity, and AI-Content Detection")
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
        help="Legacy alias for --mode (see docs); ignored if --mode is also given",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=float(os.environ.get("DEFAULT_THRESHOLD", "0.70")),
        help="Similarity threshold (0.01 - 0.99); unused in ai_code/ai_text modes",
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
        "--web",
        action="store_true",
        help=(
            "Also compare against internet search results (code_similarity/"
            "text_similarity only). Requires WEB_SEARCH_API_KEY and "
            "WEB_SEARCH_ENGINE_ID in .env."
        ),
    )

    args = parser.parse_args()
    mode = _resolve_mode(args)
    is_ai = mode in ("ai_code", "ai_text")

    web_client = None
    if args.web:
        if mode not in WEB_ELIGIBLE_MODES:
            print(f"Error: --web has no effect in mode '{mode}' (ai_code/ai_text aren't web-eligible).")
            return
        api_key = os.environ.get("WEB_SEARCH_API_KEY", "")
        engine_id = os.environ.get("WEB_SEARCH_ENGINE_ID", "")
        if not (api_key and engine_id):
            print(
                "Error: --web requires WEB_SEARCH_API_KEY and WEB_SEARCH_ENGINE_ID to be set "
                "in .env (see .env.example)."
            )
            return
        web_client = WebSearchClient(api_key=api_key, engine_id=engine_id)

    min_files = 1 if (is_ai or web_client is not None) else 2

    if not (0.01 <= args.threshold <= 0.99):
        print("Error: Threshold must be between 0.01 and 0.99")
        return

    if len(args.files) > MAX_FILES:
        print(f"Error: Batch of {len(args.files)} exceeds max of {MAX_FILES} files.")
        return

    scan_uuid = str(uuid.uuid4())
    audit = AuditLogger()
    audit.log("SCAN_START", scan_uuid=scan_uuid, payload={"files": args.files, "mode": mode})

    loader = FileLoader()
    preprocessor = Preprocessor(exclusions_path=args.exclusions)
    file_data = {}
    files_meta = []

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
            name = os.path.basename(path)
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

    if len(file_data) < min_files:
        print(f"Error: Need at least {min_files} valid file(s) for mode '{mode}'.")
        return

    print(f"Running '{mode}'{' with --web' if web_client else ''}...")
    engine = ScanEngine(mode=mode)
    result = engine.compute(
        file_data,
        preprocessor=preprocessor,
        web_client=web_client,
        max_web_queries=int(os.environ.get("WEB_SEARCH_MAX_QUERIES_PER_SCAN", "5")),
        web_budget_seconds=float(os.environ.get("WEB_SEARCH_BUDGET_SECONDS", "20")),
    )
    for warning in result.warnings:
        print(f"Warning: {warning}")

    ScanRepository().save_scan(mode, args.threshold, files_meta, result, scan_uuid)

    os.makedirs(args.output, exist_ok=True)

    if is_ai:
        _report_ai(result, args.output)
        flagged_count = sum(1 for a in result.ai_assessments.values() if a.band != "low")
    else:
        assert result.matrix is not None  # guaranteed for non-AI modes by ScanEngine.compute
        reporter = ReportGenerator()
        artifacts = reporter.generate(
            result.matrix,
            args.output,
            threshold=args.threshold,
            file_data=file_data,
            preprocessor=preprocessor,
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
        if args.format in ["csv", "both"]:
            print(f"  - {artifacts['csv']}")
        if args.format in ["html", "both"]:
            print(f"  - {artifacts['html']}")
        print(f"  - {artifacts['heatmap']}")

        if web_client is not None:
            web_report_path = _report_web_matches(result, args.output)
            print(f"  - {web_report_path}")

    audit.log("SCAN_COMPLETE", scan_uuid=scan_uuid, payload={"flagged_count": flagged_count})


def _report_web_matches(result, output_dir: str) -> str:
    """Print and persist each file's top internet-source matches.

    Only called when `--web` was passed; writes web_matches.json alongside
    the CSV/HTML/heatmap artifacts `ReportGenerator` already produced.
    """
    print("\nWeb matches (indicative — see README on internet-source scope):")
    report = {}
    for name in result.names:
        matches = result.web_matches.get(name, [])
        report[name] = [m.to_dict() for m in matches]
        if not matches:
            print(f"  {name}: no web matches found")
            continue
        for m in matches:
            print(f"  {name}: {m.score:.4f}  {m.url}  (query: {m.query!r})")

    path = os.path.join(output_dir, "web_matches.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return path


def _report_ai(result, output_dir: str) -> None:
    """Print each file's AI assessment and write ai_report.json.

    AI modes have no pairwise matrix, so the CSV/HTML/heatmap artifacts
    don't apply — this is the AI-mode equivalent of `ReportGenerator`.
    """
    print("\nAI detection results - indicative only, not evidence of misconduct:")
    report = {}
    for name in result.names:
        assessment = result.ai_assessments[name]
        print(f"  {name}: {assessment.overall_probability:.4f} ({assessment.band})")
        report[name] = assessment.to_dict()

    path = os.path.join(output_dir, "ai_report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nArtifacts generated in '{output_dir}':\n  - {path}")


if __name__ == "__main__":
    main()
