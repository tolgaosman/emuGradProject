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


def test_cli_end_to_end_ai_text_single_file(tmp_path):
    """AI modes accept a single file and write ai_report.json instead of
    the pairwise-comparison artifacts."""
    out_dir = tmp_path / "cli_ai_output"
    result = subprocess.run(
        [
            sys.executable,
            "plagcheck.py",
            "--files",
            str(SAMPLES_DIR / "sample_a.txt"),
            "--mode",
            "ai_text",
            "--output",
            str(out_dir),
        ],
        cwd=str(PLAGCHECK_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "AI detection results" in result.stdout
    assert (out_dir / "ai_report.json").is_file()


def test_cli_legacy_algorithm_alias_maps_to_mode(tmp_path):
    """--algorithm ast is documented in the graduation report; it must keep
    working, mapped onto code_similarity."""
    out_dir = tmp_path / "cli_alias_output"
    result = subprocess.run(
        [
            sys.executable,
            "plagcheck.py",
            "--files",
            str(SAMPLES_DIR / "sample_code_a.py"),
            str(SAMPLES_DIR / "sample_code_b.py"),
            "--algorithm",
            "ast",
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
    assert "legacy alias" in result.stdout
    assert "code_similarity" in result.stdout
