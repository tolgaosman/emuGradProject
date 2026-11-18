"""pdf_report.py — Full scan PDF report generator via PyMuPDF (`fitz.Story`).

Renders a printable multi-page A4 similarity report entirely in memory:
vector header banner, executive summary metrics, ranked pairwise table,
per-document Similarity Index, embedded 300-DPI similarity heatmap, and
highlighted document passages for all flagged pairs, finished with page-numbered
running footers.
"""

from __future__ import annotations

import html
import io

import pymupdf

from .matrix import ComparisonMatrix
from .reporter import (
    _PDF_WRAP_COLS,
    _highlight_segments,
    _segments_to_html,
    _wrap_segments,
    matched_spans,
)
from .similarity_index import filter_by_word_count

# Block-level `background-color` is deliberately avoided in MuPDF's `Story` CSS
# because MuPDF 1.28 replays block fills onto subsequent pages when a single
# Story spans more than one page. Inline `<span>` and `<mark>` backgrounds do
# not suffer from this and render cleanly across page breaks.
_FULL_PDF_CSS = """
body {
  font-family: sans-serif;
  font-size: 9pt;
  color: #18181b;
  line-height: 1.4;
}
h2 {
  font-size: 10.5pt;
  color: #18181b;
  margin: 12pt 0 5pt 0;
  padding-bottom: 3pt;
  border-bottom: 1px solid #d4d4d8;
}
h3 {
  font-size: 8.5pt;
  color: #52525b;
  margin: 7pt 0 2pt 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 10pt;
}
th {
  color: #52525b;
  font-size: 7.5pt;
  text-align: left;
  padding: 4pt 5pt;
  border-bottom: 1.5px solid #18181b;
}
td {
  font-size: 8.5pt;
  padding: 4.5pt 5pt;
  border-bottom: 0.5px solid #e4e4e7;
}
.kpi-table td {
  border: 0.5px solid #e4e4e7;
  padding: 5pt 7pt;
}
.kpi-label {
  color: #71717a;
  font-size: 7.5pt;
}
.kpi-val {
  font-size: 11.5pt;
  font-weight: bold;
  color: #18181b;
}
.kpi-alert {
  font-size: 11.5pt;
  font-weight: bold;
  color: #991b1b;
}
.num {
  text-align: right;
}
.pill-high {
  background-color: #fee2e2;
  color: #991b1b;
  font-weight: bold;
}
.pill-mid {
  background-color: #fef3c7;
  color: #92400e;
  font-weight: bold;
}
.pill-clear {
  background-color: #ecfdf5;
  color: #065f46;
}
.empty {
  color: #52525b;
  font-style: italic;
  margin: 4pt 0 10pt 0;
}
.pair-header {
  margin: 12pt 0 4pt 0;
  padding-bottom: 3pt;
  border-bottom: 1px solid #f5b921;
}
.pair-title {
  font-size: 10pt;
  font-weight: bold;
  color: #18181b;
  margin: 0 0 1pt 0;
}
.pair-meta {
  font-size: 8pt;
  color: #52525b;
  margin: 0;
}
pre {
  font-family: monospace;
  font-size: 7.5pt;
  line-height: 1.35;
  white-space: pre-wrap;
  border: 0.5px solid #e4e4e7;
  padding: 6pt;
  margin: 0 0 8pt 0;
}
mark {
  background-color: #fde68a;
}
.heatmap-wrap {
  text-align: center;
  margin: 6pt 0 10pt 0;
}
"""


def _score_pill(score: float, threshold: float) -> str:
    txt = f"{score * 100:.1f}%"
    if score >= 0.70:
        return f'<span class="pill-high">&nbsp;{txt}&nbsp;</span>'
    if score >= threshold or score >= 0.40:
        return f'<span class="pill-mid">&nbsp;{txt}&nbsp;</span>'
    return txt


def _render_kpi_table(
    doc_count: int,
    pair_count: int,
    flagged_count: int,
    max_score: float,
    mean_score: float,
    threshold: float,
) -> str:
    max_cls = "kpi-alert" if max_score >= threshold else "kpi-val"
    return (
        '<table class="kpi-table">'
        "<tr>"
        '<td width="25%"><span class="kpi-label">DOCUMENTS</span><br/>'
        f'<span class="kpi-val">{doc_count}</span></td>'
        '<td width="25%"><span class="kpi-label">FLAGGED / PAIRS</span><br/>'
        f'<span class="kpi-val">{flagged_count} / {pair_count}</span></td>'
        '<td width="25%"><span class="kpi-label">HIGHEST SIMILARITY</span><br/>'
        f'<span class="{max_cls}">{max_score * 100:.1f}%</span></td>'
        '<td width="25%"><span class="kpi-label">MEAN SIMILARITY</span><br/>'
        f'<span class="kpi-val">{mean_score * 100:.1f}%</span></td>'
        "</tr>"
        "</table>"
    )


def _render_pairs_table(pairs: list[dict], threshold: float) -> str:
    if not pairs:
        return '<p class="empty">Single-file scan — no pairwise comparisons generated.</p>'
    ordered = sorted(pairs, key=lambda item: float(item["score"]), reverse=True)
    rows = []
    for idx, pair in enumerate(ordered, start=1):
        score = float(pair["score"])
        flagged = bool(pair.get("flagged", score >= threshold))
        badge = (
            '<span class="pill-high">&nbsp;FLAGGED&nbsp;</span>'
            if flagged
            else '<span class="pill-clear">&nbsp;Clear&nbsp;</span>'
        )
        kgrams = pair.get("matched_kgrams")
        kg_txt = str(kgrams) if isinstance(kgrams, int) else "—"
        rows.append(
            "<tr>"
            f'<td width="6%">{idx}</td>'
            f'<td width="31%">{html.escape(str(pair["file_a"]))}</td>'
            f'<td width="31%">{html.escape(str(pair["file_b"]))}</td>'
            f'<td width="12%">{_score_pill(score, threshold)}</td>'
            f'<td width="9%" class="num">{kg_txt}</td>'
            f'<td width="11%">{badge}</td>'
            "</tr>"
        )
    return (
        "<h2>1. Pairwise Comparison Results</h2>"
        "<table><thead><tr>"
        '<th width="6%">#</th><th width="31%">Document A</th><th width="31%">Document B</th>'
        '<th width="12%">Similarity</th><th width="9%" class="num">5-grams</th>'
        '<th width="11%">Status</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _render_index_table(
    names: list[str],
    similarity_indices: dict[str, float] | None,
    source_breakdowns: dict[str, list[dict]] | None,
    threshold: float,
) -> str:
    if not similarity_indices:
        return ""
    breakdowns = source_breakdowns or {}
    ranked = sorted(names, key=lambda nm: float(similarity_indices.get(nm, 0.0)), reverse=True)
    rows = []
    for name in ranked:
        sim_idx = float(similarity_indices.get(name, 0.0))
        sources = breakdowns.get(name) or []
        top_src = html.escape(str(sources[0]["source"])) if sources else "—"
        raw_contrib = (
            sources[0].get("contribution", sources[0].get("share")) if sources else None
        )
        top_share = f"{float(raw_contrib) * 100:.1f}%" if raw_contrib is not None else "—"
        rows.append(
            "<tr>"
            f'<td width="38%">{html.escape(name)}</td>'
            f'<td width="18%">{_score_pill(sim_idx, threshold)}</td>'
            f'<td width="30%">{top_src}</td>'
            f'<td width="14%">{top_share}</td>'
            "</tr>"
        )
    return (
        "<h2>2. Per-Document Similarity Index</h2>"
        "<table><thead><tr>"
        '<th width="38%">Document</th><th width="18%">Similarity Index</th>'
        '<th width="30%">Top Source</th><th width="14%">Top Overlap</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _render_evidence_html(
    flagged: list[dict],
    file_data: dict,
    preprocessor,
    min_match_words: int,
    algorithm: str,
) -> str:
    blocks: list[str] = ["<h2>Highlighted Evidence (Flagged Pairs)</h2>"]
    ordered = sorted(flagged, key=lambda item: float(item["score"]), reverse=True)
    rendered = 0
    for idx, pair in enumerate(ordered, start=1):
        name_a, name_b = str(pair["file_a"]), str(pair["file_b"])
        score = float(pair["score"])
        data_a, data_b = file_data.get(name_a), file_data.get(name_b)
        if data_a is None or data_b is None:
            continue
        rendered += 1
        spans_a, spans_b = matched_spans(
            data_a["raw"], data_b["raw"], data_a["language"], data_b["language"], preprocessor
        )
        spans_a = filter_by_word_count(data_a["raw"], spans_a, min_match_words)
        spans_b = filter_by_word_count(data_b["raw"], spans_b, min_match_words)

        meta_bits = [f"Similarity {score * 100:.1f}%", f"Engine: {html.escape(algorithm)}"]
        if isinstance(pair.get("matched_kgrams"), int):
            meta_bits.append(f'{pair["matched_kgrams"]} matched 5-grams')

        body_a = _segments_to_html(
            _wrap_segments(_highlight_segments(data_a["raw"], spans_a), cols=_PDF_WRAP_COLS)
        )
        body_b = _segments_to_html(
            _wrap_segments(_highlight_segments(data_b["raw"], spans_b), cols=_PDF_WRAP_COLS)
        )
        blocks.append(
            '<div class="pair-header">'
            f'<p class="pair-title">Pair #{idx}: {html.escape(name_a)} &harr; '
            f"{html.escape(name_b)}</p>"
            f'<p class="pair-meta">{" &middot; ".join(meta_bits)}</p>'
            "</div>"
            f"<h3>Document A &mdash; {html.escape(name_a)}</h3>"
            f"<pre>{body_a}</pre>"
            f"<h3>Document B &mdash; {html.escape(name_b)}</h3>"
            f"<pre>{body_b}</pre>"
        )
    return "".join(blocks) if rendered > 0 else ""


def _story_to_pdf(
    doc_html: str,
    first_top_margin: float = 36.0,
    archive: pymupdf.Archive | None = None,
) -> bytes:
    story = (
        pymupdf.Story(html=doc_html, user_css=_FULL_PDF_CSS, archive=archive)
        if archive is not None
        else pymupdf.Story(html=doc_html, user_css=_FULL_PDF_CSS)
    )
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    page_rect = pymupdf.paper_rect("a4")
    page_idx = 0
    more = 1
    while more:
        top = first_top_margin if page_idx == 0 else 36.0
        content_rect = page_rect + (36, top, -36, -42)
        device = writer.begin_page(page_rect)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
        page_idx += 1
    writer.close()
    return buf.getvalue()


def _decorate_pdf(raw_pdf: bytes, meta_line: str, scan_uuid: str | None) -> bytes:
    with pymupdf.open("pdf", raw_pdf) as doc:
        # Stamp the dark header banner + amber accent rule on Page 1
        first = doc[0]
        banner = pymupdf.Rect(36, 28, first.rect.width - 36, 78)
        first.draw_rect(banner, color=None, fill=(0.094, 0.094, 0.106))
        first.draw_line(
            pymupdf.Point(36, 78),
            pymupdf.Point(first.rect.width - 36, 78),
            color=(0.96, 0.725, 0.13),
            width=2.0,
        )
        first.insert_text(
            pymupdf.Point(48, 50),
            "PlagCheck — Similarity Analysis Report",
            fontsize=13.5,
            fontname="hebo",
            color=(1.0, 1.0, 1.0),
        )
        first.insert_text(
            pymupdf.Point(48, 66),
            meta_line,
            fontsize=8.0,
            fontname="helv",
            color=(0.83, 0.83, 0.85),
        )

        # Stamp running footer + page numbers across every page
        total = len(doc)
        left_label = (
            f"PlagCheck Similarity Report · Scan {scan_uuid[:8]}"
            if scan_uuid
            else "PlagCheck Similarity Report"
        )
        for index, page in enumerate(doc, start=1):
            rect = page.rect
            y_line = rect.height - 28
            page.draw_line(
                pymupdf.Point(36, y_line),
                pymupdf.Point(rect.width - 36, y_line),
                color=(0.88, 0.88, 0.90),
                width=0.5,
            )
            page.insert_text(
                pymupdf.Point(36, rect.height - 17),
                left_label,
                fontsize=7.5,
                fontname="helv",
                color=(0.45, 0.45, 0.48),
            )
            right_label = f"Page {index} of {total}"
            right_w = pymupdf.get_text_length(right_label, fontname="helv", fontsize=7.5)
            page.insert_text(
                pymupdf.Point(rect.width - 36 - right_w, rect.height - 17),
                right_label,
                fontsize=7.5,
                fontname="helv",
                color=(0.45, 0.45, 0.48),
            )
        return doc.tobytes(deflate=True)


def build_full_pdf_bytes(
    matrix: ComparisonMatrix,
    threshold: float = 0.70,
    file_data: dict | None = None,
    preprocessor=None,
    min_match_words: int = 0,
    pairs: list[dict] | None = None,
    algorithm: str | None = None,
    mode: str | None = None,
    similarity_indices: dict[str, float] | None = None,
    source_breakdowns: dict[str, list[dict]] | None = None,
    heatmap_png: bytes | None = None,
    scan_uuid: str | None = None,
    created_at: str | None = None,
) -> bytes:
    """Render the complete multi-page A4 similarity report as PDF bytes."""
    resolved_pairs = pairs if pairs is not None else matrix.all_pairs()
    flagged = [
        p for p in resolved_pairs if bool(p.get("flagged", float(p["score"]) >= threshold))
    ]
    scores = [float(p["score"]) for p in resolved_pairs]
    max_score = max(scores, default=0.0)
    mean_score = sum(scores) / len(scores) if scores else 0.0

    algo_label = algorithm or "auto"
    mode_label = mode or "text_similarity"
    meta_items = [
        f"Mode: {mode_label}",
        f"Engine: {algo_label}",
        f"Threshold: {threshold * 100:.0f}%",
        f"Min match: {min_match_words} words",
    ]
    if scan_uuid:
        meta_items.insert(0, f"Scan {scan_uuid[:8]}")
    if created_at:
        meta_items.append(str(created_at)[:19].replace("T", " "))
    meta_line = "  ·  ".join(meta_items)

    archive = pymupdf.Archive()
    heatmap_html = ""
    if heatmap_png and len(matrix.names) >= 2:
        archive.add(heatmap_png, "heatmap.png")
        sec_num = "3" if similarity_indices else "2"
        heatmap_html = (
            f"<h2>{sec_num}. Pairwise Similarity Matrix</h2>"
            '<div class="heatmap-wrap"><img src="heatmap.png" width="420"/></div>'
        )

    no_flag_note = ""
    if not flagged:
        no_flag_note = (
            "<h2>Highlighted Evidence</h2>"
            f'<p class="empty">No document pairs reached the {threshold * 100:.0f}% alert '
            "threshold — no passages require review.</p>"
        )

    summary_html = (
        "<html><body>"
        + _render_kpi_table(
            len(matrix.names),
            len(resolved_pairs),
            len(flagged),
            max_score,
            mean_score,
            threshold,
        )
        + _render_pairs_table(resolved_pairs, threshold)
        + _render_index_table(matrix.names, similarity_indices, source_breakdowns, threshold)
        + heatmap_html
        + no_flag_note
        + "</body></html>"
    )

    summary_pdf = _story_to_pdf(summary_html, first_top_margin=90.0, archive=archive)

    if flagged and file_data is not None and preprocessor is not None:
        ev_body = _render_evidence_html(
            flagged, file_data, preprocessor, min_match_words, algo_label
        )
        if ev_body:
            ev_pdf = _story_to_pdf(f"<html><body>{ev_body}</body></html>", first_top_margin=36.0)
            with pymupdf.open("pdf", summary_pdf) as merged, pymupdf.open("pdf", ev_pdf) as tail:
                merged.insert_pdf(tail)
                summary_pdf = merged.tobytes()

    return _decorate_pdf(summary_pdf, meta_line, scan_uuid)
