""" test_reporter.py — ReportGenerator artifact generation. """
import os

from src.matrix import ComparisonMatrix
from src.reporter import ReportGenerator


def test_generate_writes_all_artifacts(tmp_path):
    """generate() writes CSV, HTML and PNG heatmap into the output dir."""
    m = ComparisonMatrix(["a.txt", "b.txt"])
    m.set(0, 1, 0.85)

    out = str(tmp_path / "reports")
    artifacts = ReportGenerator().generate(m, out, threshold=0.70)

    for key in ("csv", "html", "heatmap"):
        assert os.path.isfile(artifacts[key]), f"{key} not written"

    html = open(artifacts["html"], encoding="utf-8").read()
    assert "a.txt" in html and "b.txt" in html
    assert "0.8500" in html  # flagged pair rendered
