""" test_cli.py — plagcheck.py CLI import and end-to-end smoke tests.

Regression guard for the class of bug where the CLI silently breaks (e.g. an
import that no longer resolves after a refactor) while the pytest suite stays
green because nothing else imports plagcheck.py.
"""
import subprocess
import sys
from pathlib import Path

PLAGCHECK_DIR = Path(__file__).resolve().parent.parent / "plagcheck"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


def test_plagcheck_module_imports_cleanly():
    """plagcheck.py must import without error — this is exactly the bug
    that hid behind a green test suite when engine.AlgorithmEngine was
    renamed but the CLI's import wasn't updated."""
    result = subprocess.run(
        [sys.executable, "-c", "import plagcheck"],
        cwd=str(PLAGCHECK_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, "plagcheck.py", "--help"],
        cwd=str(PLAGCHECK_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--mode" in result.stdout
    assert "--algorithm" in result.stdout


def test_cli_end_to_end_code_similarity(tmp_path):
    """Runs the real CLI subprocess against the sample Python pair and
    checks it produces the documented artifacts, end to end."""
    out_dir = tmp_path / "cli_output"
    result = subprocess.run(
        [
            sys.executable,
            "plagcheck.py",
            "--files",
            str(SAMPLES_DIR / "sample_code_a.py"),
            str(SAMPLES_DIR / "sample_code_b.py"),
            "--mode",
            "code_similarity",
            "--threshold",
            "0.4",
            "--output",
            str(out_dir),
        ],
        cwd=str(PLAGCHECK_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "Scan complete" in result.stdout
    assert (out_dir / "similarity_matrix.csv").is_file()
    assert (out_dir / "comparison_report.html").is_file()
    assert (out_dir / "similarity_heatmap.png").is_file()


def _run_cli(tmp_path, out_name: str, *extra_args: str):
    out_dir = tmp_path / out_name
    result = subprocess.run(
        [
            sys.executable,
            "plagcheck.py",
            "--files",
            str(SAMPLES_DIR / "sample_code_a.py"),
            str(SAMPLES_DIR / "sample_code_b.py"),
            "--threshold",
            "0.4",
            "--output",
            str(out_dir),
            *extra_args,
        ],
        cwd=str(PLAGCHECK_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result, out_dir


def _flagged_scores(stdout: str) -> list[float]:
    """Parse the `a <-> b : 0.1234` lines out of the CLI's flagged summary."""
    return [float(line.rsplit(":", 1)[1]) for line in stdout.splitlines() if " <-> " in line]


def test_cli_algorithm_selects_mode_and_forces_algorithm(tmp_path):
    """--algorithm ast is documented in the graduation report. It must both
    select code_similarity *and* actually run AST — it previously only
    mapped to a mode, so the requested algorithm was silently ignored."""
    result, _ = _run_cli(tmp_path, "cli_ast_output", "--algorithm", "ast")
    assert "code_similarity" in result.stdout
    assert "algorithm: ast" in result.stdout


def test_cli_flags_the_sample_pair(tmp_path):
    """The sample pair is B renamed from A — the fixture the report demos.
    It must actually come back flagged, not merely exit 0 with an empty
    result, which is what the older artifact-existence assertions allowed."""
    result, _ = _run_cli(tmp_path, "cli_flagged_output", "--mode", "code_similarity")
    scores = _flagged_scores(result.stdout)
    assert scores, f"expected the renamed sample pair to be flagged:\n{result.stdout}"
    assert scores[0] >= 0.4


def test_cli_algorithm_changes_the_score(tmp_path):
    """Forcing an algorithm must actually change scoring, not silently fall
    through to the default."""
    default, _ = _run_cli(tmp_path, "cli_default", "--mode", "code_similarity")
    jaccard, _ = _run_cli(tmp_path, "cli_jaccard", "--algorithm", "jaccard", "--mode",
                          "code_similarity")
    assert _flagged_scores(default.stdout) != _flagged_scores(jaccard.stdout)


def test_cli_format_csv_skips_html(tmp_path):
    """--format gates artifact *generation*, not just which paths get printed."""
    _, out_dir = _run_cli(tmp_path, "cli_csv_only", "--mode", "code_similarity",
                          "--format", "csv")
    assert (out_dir / "similarity_matrix.csv").is_file()
    assert not (out_dir / "comparison_report.html").exists()


def test_cli_exits_nonzero_when_no_file_is_valid(tmp_path):
    """A scan that can't run must fail loudly — main() used to print
    "Error: ..." and still exit 0, so callers couldn't detect it."""
    result = subprocess.run(
        [
            sys.executable,
            "plagcheck.py",
            "--files",
            str(SAMPLES_DIR / "sample_code_a.py"),  # .py is rejected by text mode
            "--mode",
            "text_similarity",
            "--output",
            str(tmp_path / "cli_invalid"),
        ],
        cwd=str(PLAGCHECK_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "Need at least 1 valid file" in result.stdout
