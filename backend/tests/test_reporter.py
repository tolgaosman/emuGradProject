""" test_reporter.py — ReportGenerator artifact generation. """
import os

import pymupdf

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
    with pymupdf.open("pdf", pdf) as doc:
        return "".join(str(page.get_text("text")) for page in doc)


def _pdf_fill_count(pdf: bytes) -> int:
    """Number of filled rectangles drawn — i.e. rendered <mark> backgrounds."""
    with pymupdf.open("pdf", pdf) as doc:
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


def test_paired_spans_links_prose_and_c_family_renamed_code():
    """paired_spans returns synchronized (span_a, span_b) blocks for both
    literal prose overlaps and renamed C/C++/Java structural functions."""
    from src.reporter import paired_spans

    pre = Preprocessor(exclusions_path="__no_such_file__")
    prose_a = (
        "Intro note. Machine learning models require careful validation "
        "before deployment in production systems."
    )
    prose_b = (
        "Header line.\n\nMachine learning models require careful validation "
        "before deployment in production systems!"
    )
    linked = paired_spans(prose_a, prose_b, "text", "text", pre, min_match_words=5)
    assert len(linked) == 1
    assert linked[0]["kind"] == "literal"
    sa, ea = linked[0]["span_a"]
    sb, eb = linked[0]["span_b"]
    assert "Machine learning" in prose_a[sa:ea]
    assert "Machine learning" in prose_b[sb:eb]

    cpp_a = (
        "int computeSum(int* arr, int count) {\n"
        "    int total = 0;\n"
        "    for (int i = 0; i < count; i++) {\n"
        "        if (arr[i] > 0) { total += arr[i]; }\n"
        "    }\n"
        "    return total;\n"
        "}\n"
    )
    cpp_b = (
        "int addPositive(int* items, int length) {\n"
        "    int acc = 0;\n"
        "    for (int k = 0; k < length; k++) {\n"
        "        if (items[k] > 0) { acc += items[k]; }\n"
        "    }\n"
        "    return acc;\n"
        "}\n"
    )
    spans_a, spans_b = matched_spans(cpp_a, cpp_b, "cpp", "cpp", pre)
    assert spans_a and spans_b
    struct_linked = paired_spans(cpp_a, cpp_b, "cpp", "cpp", pre, min_match_words=5)
    assert any(item["kind"] == "structural" for item in struct_linked)


def test_excel_bytes_builds_valid_three_sheet_ooxml_workbook():
    """excel_bytes emits a valid 3-sheet .xlsx ZIP package with well-formed XML
    parts, numeric similarity scores, and preserved non-ASCII filenames."""
    import io
    import xml.etree.ElementTree as ET
    import zipfile

    m = ComparisonMatrix(["Ödev_1, final.docx", "Ödev_2.docx", "unrelated.txt"])
    m.set(0, 1, 0.92)
    m.set(0, 2, 0.22)
    m.set(1, 2, 0.05)

    xlsx = ReportGenerator().excel_bytes(
        m,
        threshold=0.70,
        pairs=[
            {"file_a": "Ödev_1, final.docx", "file_b": "Ödev_2.docx", "score": 0.92,
             "matched_kgrams": 41, "flagged": True},
            {"file_a": "Ödev_1, final.docx", "file_b": "unrelated.txt", "score": 0.22,
             "matched_kgrams": 3, "flagged": False},
            {"file_a": "Ödev_2.docx", "file_b": "unrelated.txt", "score": 0.05,
             "flagged": False},
        ],
        mode="text_similarity",
        algorithm="auto",
        min_match_words=8,
        similarity_indices={"Ödev_1, final.docx": 0.92, "Ödev_2.docx": 0.88, "unrelated.txt": 0.0},
        source_breakdowns={
            "Ödev_1, final.docx": [{"source": "Ödev_2.docx", "contribution": 0.92}],
            "Ödev_2.docx": [{"source": "Ödev_1, final.docx", "contribution": 0.88}],
        },
        scan_uuid="12345678-1234-1234-1234-123456789abc",
        created_at="2026-11-18T11:30:00Z",
    )
    assert xlsx[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(xlsx)) as zf:
        names = set(zf.namelist())
        assert {
            "[Content_Types].xml",
            "xl/workbook.xml",
            "xl/styles.xml",
            "xl/sharedStrings.xml",
            "xl/worksheets/sheet1.xml",
            "xl/worksheets/sheet2.xml",
            "xl/worksheets/sheet3.xml",
        }.issubset(names)
        for member in names:
            if member.endswith(".xml") or member.endswith(".rels"):
                ET.fromstring(zf.read(member))
        shared_xml = zf.read("xl/sharedStrings.xml").decode("utf-8")
        assert "Ödev_1, final.docx" in shared_xml
        assert "FLAGGED" in shared_xml

    # Single-file empty-pair edge case must also serialize cleanly
    single = ReportGenerator().excel_bytes(ComparisonMatrix(["solo.txt"]), threshold=0.70)
    with zipfile.ZipFile(io.BytesIO(single)) as zf:
        ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))


def test_full_pdf_bytes_embeds_summary_heatmap_and_highlighted_evidence():
    """full_pdf_bytes renders an A4 multi-section PDF with summary tables,
    embedded heatmap image, highlighted passages, and stamped page footers."""
    pre = Preprocessor(exclusions_path="__no_such_file__")
    prose_a = (
        "Distributed consensus protocols maintain state machine safety across "
        "replicated cluster nodes during network partitions."
    )
    prose_b = (
        "Summary: distributed consensus protocols maintain state machine safety across "
        "replicated cluster nodes during network partitions!"
    )
    file_data = {
        "İzin_A.txt": {"raw": prose_a, "language": "text"},
        "B_copy.txt": {"raw": prose_b, "language": "text"},
    }
    m = ComparisonMatrix(["İzin_A.txt", "B_copy.txt"])
    m.set(0, 1, 0.88)

    pdf = ReportGenerator().full_pdf_bytes(
        m,
        threshold=0.70,
        file_data=file_data,
        preprocessor=pre,
        min_match_words=5,
        pairs=[{
            "file_a": "İzin_A.txt",
            "file_b": "B_copy.txt",
            "score": 0.88,
            "matched_kgrams": 11,
            "flagged": True,
        }],
        algorithm="auto",
        mode="text_similarity",
        similarity_indices={"İzin_A.txt": 0.88, "B_copy.txt": 0.84},
        source_breakdowns={"İzin_A.txt": [{"source": "B_copy.txt", "contribution": 0.88}]},
        scan_uuid="abcdef12-0000-0000-0000-000000000000",
        created_at="2026-11-18T11:30:00Z",
    )
    assert pdf[:5] == b"%PDF-"
    text = _pdf_text(pdf)
    assert "PlagCheck" in text
    assert "İzin_A.txt" in text
    assert "88.0%" in text
    assert "FLAGGED" in text
    assert "Page 1 of" in text
    with pymupdf.open("pdf", pdf) as doc:
        assert sum(len(page.get_images()) for page in doc) >= 1

    # Unflagged / no-evidence scan renders cleanly too
    low_m = ComparisonMatrix(["a.txt", "b.txt"])
    low_m.set(0, 1, 0.12)
    low_pdf = ReportGenerator().full_pdf_bytes(low_m, threshold=0.70)
    assert "70% alert threshold" in _pdf_text(low_pdf)
