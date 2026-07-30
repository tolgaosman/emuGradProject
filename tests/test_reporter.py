""" test_reporter.py — ReportGenerator artifact generation. """
import os

from src.matrix import ComparisonMatrix
from src.preprocessor import Preprocessor
from src.reporter import ReportGenerator, matched_spans


def test_generate_writes_all_artifacts(tmp_path):
    """generate() writes CSV, HTML and PNG heatmap into the output dir."""
    m = ComparisonMatrix(["a.txt", "b.txt"])
    m.set(0, 1, 0.85)

    out = str(tmp_path / "reports")
    artifacts = ReportGenerator().generate(m, out, threshold=0.70)

    for key in ("csv", "html", "heatmap"):
        assert os.path.isfile(artifacts[key]), f"{key} not written"

    with open(artifacts["html"], encoding="utf-8") as f:
        html = f.read()
    assert "a.txt" in html and "b.txt" in html
    assert "0.8500" in html  # flagged pair rendered


def test_generate_with_no_flagged_pairs_renders_empty_state(tmp_path):
    """When nothing meets the threshold, the summary shows the empty state."""
    m = ComparisonMatrix(["a.txt", "b.txt"])
    m.set(0, 1, 0.10)

    out = str(tmp_path / "reports")
    artifacts = ReportGenerator().generate(m, out, threshold=0.70)

    with open(artifacts["html"], encoding="utf-8") as f:
        html = f.read()
    assert "nothing to review" in html


def test_generate_side_by_side_highlights_prose_and_python(tmp_path):
    """With file_data + preprocessor, both a prose and a Python pair render
    side-by-side panes with <mark> spans over the raw source."""
    pre = Preprocessor(exclusions_path="__no_such_file__")

    prose_a = "the quick brown fox jumps over the lazy dog near the river bank today"
    prose_b = "a quick brown fox jumps over a lazy dog near the river bank yesterday"
    code_a = "def add(a, b):\n    result = a + b\n    return result\n"
    code_b = "def add(a, b):\n    result = a + b\n    return result\n"

    file_data = {
        "a.txt": {"raw": prose_a, "tokens": [], "kgrams": [], "is_python": False},
        "b.txt": {"raw": prose_b, "tokens": [], "kgrams": [], "is_python": False},
        "a.py": {"raw": code_a, "tokens": [], "kgrams": [], "is_python": True},
        "b.py": {"raw": code_b, "tokens": [], "kgrams": [], "is_python": True},
    }
    m = ComparisonMatrix(["a.txt", "b.txt", "a.py", "b.py"])
    m.set(0, 1, 0.85)
    m.set(2, 3, 1.00)
    m.set(0, 2, 0.0)
    m.set(0, 3, 0.0)
    m.set(1, 2, 0.0)
    m.set(1, 3, 0.0)

    out = str(tmp_path / "reports")
    artifacts = ReportGenerator().generate(
        m, out, threshold=0.70, file_data=file_data, preprocessor=pre
    )

    with open(artifacts["html"], encoding="utf-8") as f:
        html = f.read()
    assert "side-by-side" in html
    assert "<mark>" in html
    assert "a.txt &harr; b.txt" in html
    assert "a.py &harr; b.py" in html


def test_matched_spans_falls_back_to_prose_for_unparseable_python():
    """A Python file that fails to tokenize still yields sensible spans via
    the prose fallback path, instead of raising."""
    pre = Preprocessor(exclusions_path="__no_such_file__")
    broken = "def broken(:\n    return\n"
    ok = "def broken(x):\n    return x\n"

    spans_a, spans_b = matched_spans(broken, ok, True, True, pre)
    assert isinstance(spans_a, list)
    assert isinstance(spans_b, list)


def test_matched_spans_no_overlap_returns_empty_lists():
    """Completely dissimilar texts produce no matched spans."""
    pre = Preprocessor(exclusions_path="__no_such_file__")
    spans_a, spans_b = matched_spans(
        "alpha beta gamma delta epsilon zeta",
        "unrelated words entirely different",
        False,
        False,
        pre,
    )
    assert spans_a == []
    assert spans_b == []


def test_heatmap_png_bytes_returns_valid_png_signature():
    m = ComparisonMatrix(["a.txt", "b.txt"])
    m.set(0, 1, 0.5)
    png = ReportGenerator().heatmap_png_bytes(m, threshold=0.70)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
