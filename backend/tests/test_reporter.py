""" test_reporter.py — ReportGenerator artifact generation. """
import os

import fitz
from src.matrix import ComparisonMatrix
from src.preprocessor import Preprocessor
from src.reporter import (
    ReportGenerator,
    _highlight,
    _highlight_segments,
    _wrap_segments,
    matched_spans,
)


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


def test_single_row_heatmap_png_bytes():
    """single_row_heatmap_png_bytes returns valid PNG bytes for 1xK matrix."""
    png = ReportGenerator().single_row_heatmap_png_bytes(
        "sample_a.txt", ["sample_b.txt", "sample_c.docx", "sample_d.pdf"], [0.44, 1.00, 1.00], 0.70
    )
    assert isinstance(png, bytes)
    assert len(png) > 0
    assert png.startswith(b"\x89PNG")


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
        "a.txt": {"raw": prose_a, "tokens": [], "kgrams": [], "language": "text"},
        "b.txt": {"raw": prose_b, "tokens": [], "kgrams": [], "language": "text"},
        "a.py": {"raw": code_a, "tokens": [], "kgrams": [], "language": "python"},
        "b.py": {"raw": code_b, "tokens": [], "kgrams": [], "language": "python"},
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

    spans_a, spans_b = matched_spans(broken, ok, "python", "python", pre)
    assert isinstance(spans_a, list)
    assert isinstance(spans_b, list)


def test_matched_spans_no_overlap_returns_empty_lists():
    """Completely dissimilar texts produce no matched spans."""
    pre = Preprocessor(exclusions_path="__no_such_file__")
    spans_a, spans_b = matched_spans(
        "alpha beta gamma delta epsilon zeta",
        "unrelated words entirely different",
        "text",
        "text",
        pre,
    )
    assert spans_a == []
    assert spans_b == []


def test_heatmap_png_bytes_returns_valid_png_signature():
    m = ComparisonMatrix(["a.txt", "b.txt"])
    m.set(0, 1, 0.5)
    png = ReportGenerator().heatmap_png_bytes(m, threshold=0.70)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def _pdf_text(pdf: bytes) -> str:
    with fitz.open("pdf", pdf) as doc:
        return "".join(str(page.get_text("text")) for page in doc)


def _pdf_fill_count(pdf: bytes) -> int:
    """Number of filled rectangles drawn — i.e. rendered <mark> backgrounds."""
    with fitz.open("pdf", pdf) as doc:
        return sum(len([d for d in page.get_drawings() if d["fill"]]) for page in doc)


def test_pair_pdf_bytes_contains_both_documents():
    """The export reproduces both documents in full, under their own names,
    so the reader can see what matched what."""
    text_a = "Machine learning models require careful validation before deployment."
    text_b = "Every pipeline: machine learning models require careful validation."
    pdf = ReportGenerator().pair_pdf_bytes(
        "reference.txt", text_a, [(0, 52)],
        "candidate.txt", text_b, [(17, 69)],
        score=0.62, threshold=0.70, mode="text_similarity", algorithm="auto",
    )
    assert pdf[:5] == b"%PDF-"

    out = _pdf_text(pdf)
    assert "reference.txt" in out
    assert "candidate.txt" in out
    assert "Machine learning models require careful validation" in out
    assert "62.0%" in out
    assert "Below threshold" in out


def test_pair_pdf_bytes_renders_highlights():
    """A matched span must produce an actual painted background, not just
    markup — the highlighting is the whole point of the export."""
    text = "alpha beta gamma delta epsilon zeta eta theta"
    gen = ReportGenerator()
    highlighted = gen.pair_pdf_bytes("a.txt", text, [(0, 16)], "b.txt", text, [(0, 16)])
    plain = gen.pair_pdf_bytes("a.txt", text, [], "b.txt", text, [])
    assert _pdf_fill_count(highlighted) > _pdf_fill_count(plain)


def test_pair_pdf_bytes_preserves_non_ascii():
    """Turkish text must survive layout — the display names the API passes
    here are the browser's untouched File.name values."""
    turkish = "İşçi Şükrü ğüöç değerlendirme"
    pdf = ReportGenerator().pair_pdf_bytes("İzin.txt", turkish, [], "b.txt", turkish, [])
    assert "İşçi Şükrü ğüöç" in _pdf_text(pdf)


def test_pair_pdf_bytes_omits_unknown_metadata():
    """When the scan record can't be read back, the header states no score
    rather than inventing one."""
    pdf = ReportGenerator().pair_pdf_bytes("a.txt", "alpha beta", [], "b.txt", "alpha beta", [])
    out = _pdf_text(pdf)
    assert "Matched regions highlighted" in out
    assert "%" not in out


def test_pair_pdf_bytes_does_not_clip_unbroken_runs():
    """MuPDF's story engine clips (not wraps) a run wider than the line box,
    so a minified file would silently lose most of its text without
    `_wrap_segments`."""
    run = "x" * 600
    pdf = ReportGenerator().pair_pdf_bytes("a.txt", run, [], "b.txt", run, [])
    assert _pdf_text(pdf).count("x") >= 1200


def test_wrap_segments_breaks_long_runs_without_moving_boundaries():
    wrapped = _wrap_segments([("a" * 250, False), ("b" * 30, True)], cols=100)
    assert "".join(chunk for chunk, _ in wrapped).replace("\n", "") == "a" * 250 + "b" * 30
    assert [marked for _, marked in wrapped] == [False, True]
    assert max(len(line) for line in "".join(c for c, _ in wrapped).split("\n")) <= 100


def test_wrap_segments_resets_the_column_at_real_newlines():
    wrapped = _wrap_segments([("short\n" + "y" * 40, False)], cols=100)
    assert wrapped[0][0] == "short\n" + "y" * 40  # nothing added


def test_highlight_segments_round_trips_the_original_text():
    text = "alpha beta gamma delta"
    segments = _highlight_segments(text, [(0, 5), (11, 16)])
    assert "".join(chunk for chunk, _ in segments) == text
    assert [chunk for chunk, marked in segments if marked] == ["alpha", "gamma"]


def test_highlight_still_emits_mark_tags_after_the_segment_refactor():
    assert _highlight("alpha beta", [(0, 5)]) == "<mark>alpha</mark> beta"
    assert _highlight("a < b", []) == "a &lt; b"
