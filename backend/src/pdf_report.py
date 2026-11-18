"""pdf_report.py — Clean, plain-paper PDF reports via PyMuPDF."""

from __future__ import annotations

import html
import io
import re

import pymupdf

from .language import CODE_LANGUAGES
from .matrix import ComparisonMatrix
from .models import ASTModel, CosineModel, JaccardModel, WinnowingModel
from .reporter import (
    _highlight_segments,
    _segments_to_html,
    matched_spans,
    model_spans,
)
from .similarity_index import filter_by_word_count, pair_score

_LONG_RUN_RE = re.compile(r"\S{85,}")

_PDF_CSS = """
body {
  font-family: sans-serif;
  font-size: 9.2pt;
  color: #1c1917;
  line-height: 1.5;
}
h1 {
  font-size: 13pt;
  font-weight: bold;
  color: #1c1917;
  margin: 0 0 2pt 0;
}
.sub {
  font-size: 8.5pt;
  color: #57534e;
  margin: 0 0 12pt 0;
  padding-bottom: 7pt;
  border-bottom: 0.5px solid #d6d3d1;
}
h2 {
  font-size: 9.5pt;
  font-weight: bold;
  color: #1c1917;
  margin: 14pt 0 5pt 0;
}
.file-label {
  font-size: 8.5pt;
  font-weight: bold;
  color: #44403c;
  margin: 10pt 0 4pt 0;
}
.prose-body {
  font-family: sans-serif;
  font-size: 8.6pt;
  line-height: 1.44;
  color: #1c1917;
  white-space: pre-wrap;
  margin: 0 0 8pt 0;
}
pre.code-body {
  font-family: monospace;
  font-size: 7.8pt;
  line-height: 1.4;
  color: #1c1917;
  white-space: pre-wrap;
  margin: 0 0 12pt 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 12pt;
}
th {
  color: #57534e;
  font-size: 8pt;
  font-weight: bold;
  text-align: left;
  padding: 4pt 5pt;
  border-bottom: 0.75px solid #a8a29e;
}
td {
  font-size: 8.5pt;
  padding: 4pt 5pt;
  border-bottom: 0.5px solid #e7e5e4;
}
.num {
  text-align: right;
}
.muted {
  color: #78716c;
}
.flagged {
  color: #991b1b;
  font-weight: bold;
}
.pair-divider {
  margin: 14pt 0 4pt 0;
  padding-top: 8pt;
  border-top: 0.5px solid #d6d3d1;
}
.pair-names {
  font-size: 9.5pt;
  font-weight: bold;
  color: #1c1917;
  margin: 0 0 2pt 0;
}
mark {
  background-color: #fef3c7;
}
.heatmap-wrap {
  text-align: center;
  margin: 6pt 0 10pt 0;
}
"""

_MODEL_LABELS: dict[str, str] = {
    "coverage": "Coverage",
    "ast": "AST Structure",
    "cosine": "TF-IDF Cosine",
    "winnowing": "Winnowing",
    "jaccard": "Jaccard",
}


def _break_unbroken_runs(
    segments: list[tuple[str, bool]], max_run: int = 85
) -> list[tuple[str, bool]]:
    """Split single non-whitespace tokens wider than `max_run` chars."""

    def _split_match(m: re.Match[str]) -> str:
        s = m.group(0)
        return "\n".join(s[i : i + max_run] for i in range(0, len(s), max_run))

    return [(_LONG_RUN_RE.sub(_split_match, chunk), marked) for chunk, marked in segments]


def _is_code_file(name: str, mode: str | None = None) -> bool:
    if mode == "code_similarity":
        return True
    lower = name.lower()
    return lower.endswith((".py", ".java", ".c", ".h", ".cpp", ".cc", ".hpp"))


def _score_span(score: float, threshold: float) -> str:
    txt = f"{score * 100:.1f}%"
    return f'<span class="flagged">{txt}</span>' if score >= threshold else txt


def _render_doc_block(
    role: str, name: str, text: str, spans: list[tuple[int, int]], is_code: bool
) -> str:
    segments = _break_unbroken_runs(_highlight_segments(text, spans))
    inner = _segments_to_html(segments)
    tag = (
        f'<pre class="code-body">{inner}</pre>'
        if is_code
        else f'<div class="prose-body">{inner}</div>'
    )
    return f'<p class="file-label">{html.escape(role)}: {html.escape(name)}</p>{tag}'


def _render_doc_pair(
    name_a: str,
    text_a: str,
    spans_a: list[tuple[int, int]],
    name_b: str,
    text_b: str,
    spans_b: list[tuple[int, int]],
    mode: str | None = None,
) -> str:
    note = (
        '<p class="muted">No shared segments for this model.</p>'
        if not spans_a and not spans_b
        else ""
    )
    return (
        note
        + _render_doc_block("Reference File", name_a, text_a, spans_a, _is_code_file(name_a, mode))
        + _render_doc_block(
            "File to be Checked", name_b, text_b, spans_b, _is_code_file(name_b, mode)
        )
    )


def _render_story(doc_html: str, archive: pymupdf.Archive | None = None) -> bytes:
    story = (
        pymupdf.Story(html=doc_html, user_css=_PDF_CSS, archive=archive)
        if archive is not None
        else pymupdf.Story(html=doc_html, user_css=_PDF_CSS)
    )
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    page_rect = pymupdf.paper_rect("a4")
    content_rect = page_rect + (44, 42, -44, -44)
    more = 1
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
    writer.close()
    return buf.getvalue()


def _stamp_footers(raw_pdf: bytes, include_brand: bool = False) -> bytes:
    with pymupdf.open("pdf", raw_pdf) as doc:
        total = len(doc)
        for idx, page in enumerate(doc, start=1):
            rect = page.rect
            if include_brand:
                page.insert_text(
                    pymupdf.Point(44, rect.height - 20),
                    "PlagCheck",
                    fontsize=7.5,
                    fontname="helv",
                    color=(0.55, 0.53, 0.51),
                )
            right = f"{idx} / {total}"
            rw = pymupdf.get_text_length(right, fontname="helv", fontsize=7.5)
            page.insert_text(
                pymupdf.Point(rect.width - 44 - rw, rect.height - 20),
                right,
                fontsize=7.5,
                fontname="helv",
                color=(0.55, 0.53, 0.51),
            )
        return doc.tobytes(deflate=True)


def _model_scores_table_html(
    algo_scores: dict[str, float | None], threshold: float | None
) -> str:
    thr = threshold if threshold is not None else 0.70
    rows = []
    for key in ("coverage", "ast", "cosine", "winnowing", "jaccard"):
        val = algo_scores.get(key)
        if val is None:
            continue
        rows.append(
            "<tr>"
            f'<td width="70%">{html.escape(_MODEL_LABELS[key])}</td>'
            f'<td width="30%" class="num">{_score_span(float(val), thr)}</td>'
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        '<th width="70%">Model</th><th width="30%" class="num">Similarity</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _append_model_pages(
    base_doc: pymupdf.Document,
    name_a: str,
    text_a: str,
    name_b: str,
    text_b: str,
    algo_scores: dict[str, float | None],
    per_model_spans: dict[str, dict[str, list[tuple[int, int]]]],
    mode: str | None = None,
) -> None:
    pair_sub = f"{html.escape(name_a)}  vs  {html.escape(name_b)}"
    for key in ("ast", "cosine", "winnowing", "jaccard"):
        val = algo_scores.get(key)
        if val is None:
            continue
        label = _MODEL_LABELS[key]
        m_spans = per_model_spans.get(key, {"a": [], "b": []})
        spans_a = [(int(s), int(e)) for s, e in m_spans.get("a", [])]
        spans_b = [(int(s), int(e)) for s, e in m_spans.get("b", [])]
        section_html = (
            "<html><body>"
            f"<h1>{html.escape(label)} ({float(val) * 100:.1f}%)</h1>"
            f'<p class="sub">{pair_sub}</p>'
            + _render_doc_pair(name_a, text_a, spans_a, name_b, text_b, spans_b, mode=mode)
            + "</body></html>"
        )
        sec_bytes = _render_story(section_html)
        with pymupdf.open("pdf", sec_bytes) as sec_doc:
            base_doc.insert_pdf(sec_doc)


def build_pair_pdf_bytes(
    name_a: str,
    text_a: str,
    spans_a: list[tuple[int, int]],
    name_b: str,
    text_b: str,
    spans_b: list[tuple[int, int]],
    score: float | None = None,
    threshold: float | None = None,
    mode: str | None = None,
    algorithm: str | None = None,
    algorithm_scores: dict[str, float | None] | None = None,
    per_model_spans: dict[str, dict[str, list[tuple[int, int]]]] | None = None,
    scan_uuid: str | None = None,
) -> bytes:
    """Render a clean 1-vs-1 PDF report with one dedicated page section per model."""
    _ = scan_uuid
    meta = []
    if score is not None:
        meta.append(f"{score * 100:.1f}%")
        if threshold is not None:
            meta.append("Flagged" if score >= threshold else "Below threshold")
    if threshold is not None:
        meta.append(f"threshold {threshold:.2f}")
    if mode:
        meta.append(html.escape(mode.replace("_", " ")))
    if algorithm and algorithm != "auto":
        meta.append(html.escape(algorithm))

    summary_table = (
        _model_scores_table_html(algorithm_scores, threshold)
        if algorithm_scores is not None
        else ""
    )
    cov_heading = ""
    if algorithm_scores is not None and algorithm_scores.get("coverage") is not None:
        cov_pct = float(algorithm_scores["coverage"]) * 100
        cov_heading = f"<h2>Coverage ({cov_pct:.1f}%)</h2>"

    first_html = (
        "<html><body>"
        f"<h1>{html.escape(name_a)}  vs  {html.escape(name_b)}</h1>"
        f'<p class="sub">{" · ".join(meta) or "Matched regions highlighted"}</p>'
        + summary_table
        + cov_heading
        + _render_doc_pair(name_a, text_a, spans_a, name_b, text_b, spans_b, mode=mode)
        + "</body></html>"
    )
    pdf_bytes = _render_story(first_html)

    if algorithm_scores is not None and per_model_spans is not None:
        with pymupdf.open("pdf", pdf_bytes) as doc:
            _append_model_pages(
                doc, name_a, text_a, name_b, text_b, algorithm_scores, per_model_spans, mode=mode
            )
            pdf_bytes = doc.tobytes()
        return _stamp_footers(pdf_bytes)

    return pdf_bytes


def _pairs_table_html(pairs: list[dict], threshold: float) -> str:
    if not pairs:
        return '<p class="muted">Single file uploaded.</p>'
    ordered = sorted(pairs, key=lambda item: float(item["score"]), reverse=True)
    rows = []
    for pair in ordered:
        score = float(pair["score"])
        flagged = bool(pair.get("flagged", score >= threshold))
        kgrams = pair.get("matched_kgrams")
        kg_txt = str(kgrams) if isinstance(kgrams, int) else "-"
        status_html = '<span class="flagged">Flagged</span>' if flagged else ""
        rows.append(
            "<tr>"
            f'<td width="35%">{html.escape(str(pair["file_a"]))}</td>'
            f'<td width="35%">{html.escape(str(pair["file_b"]))}</td>'
            f'<td width="12%" class="num">{_score_span(score, threshold)}</td>'
            f'<td width="9%" class="num muted">{kg_txt}</td>'
            f'<td width="9%">{status_html}</td>'
            "</tr>"
        )
    return (
        "<h2>Pairs</h2>"
        "<table><thead><tr>"
        '<th width="35%">Reference File</th><th width="35%">File to be Checked</th>'
        '<th width="12%" class="num">Similarity</th>'
        '<th width="9%" class="num">5-grams</th><th width="9%"></th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _files_table_html(
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
        sim = float(similarity_indices.get(name, 0.0))
        sources = breakdowns.get(name) or []
        if sources:
            top_name = html.escape(str(sources[0]["source"]))
            raw_c = sources[0].get("contribution", sources[0].get("share"))
            closest = (
                f"{top_name} ({float(raw_c) * 100:.1f}%)" if raw_c is not None else top_name
            )
        else:
            closest = ""
        rows.append(
            "<tr>"
            f'<td width="42%">{html.escape(name)}</td>'
            f'<td width="16%" class="num">{_score_span(sim, threshold)}</td>'
            f'<td width="42%" class="muted">{closest}</td>'
            "</tr>"
        )
    return (
        "<h2>Files</h2>"
        "<table><thead><tr>"
        '<th width="42%">File</th><th width="16%" class="num">Matched</th>'
        '<th width="42%">Closest file</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _compute_pair_models(
    raw_a: str,
    lang_a: str,
    spans_a: list[tuple[int, int]],
    raw_b: str,
    lang_b: str,
    spans_b: list[tuple[int, int]],
    preprocessor,
) -> tuple[dict[str, float | None], dict[str, dict[str, list[tuple[int, int]]]]]:
    tokens_a, _ = preprocessor.process(raw_a, lang_a)
    tokens_b, _ = preprocessor.process(raw_b, lang_b)
    ast_val = (
        round(ASTModel().compute([raw_a], [raw_b]), 4)
        if lang_a == "python" and lang_b == "python"
        else None
    )
    scores: dict[str, float | None] = {
        "coverage": round(pair_score(raw_a, raw_b, spans_a, spans_b), 4),
        "cosine": round(CosineModel().compute(tokens_a, tokens_b), 4),
        "winnowing": round(WinnowingModel().compute(tokens_a, tokens_b), 4),
        "jaccard": round(JaccardModel().compute(tokens_a, tokens_b), 4),
        "ast": ast_val,
    }
    return scores, model_spans(raw_a, raw_b, lang_a, lang_b, preprocessor)


def _evidence_html(
    flagged: list[dict],
    file_data: dict,
    preprocessor,
    min_match_words: int,
    mode: str | None,
) -> str:
    blocks: list[str] = ["<h2>Matched passages</h2>"]
    ordered = sorted(flagged, key=lambda item: float(item["score"]), reverse=True)
    rendered = 0
    for pair in ordered:
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
        pair_mode = (
            "code_similarity"
            if data_a["language"] in CODE_LANGUAGES or data_b["language"] in CODE_LANGUAGES
            else mode
        )
        blocks.append(
            '<div class="pair-divider">'
            f'<p class="pair-names">{html.escape(name_a)}  vs  {html.escape(name_b)} '
            f"({score * 100:.1f}%)</p>"
            "</div>"
            + _render_doc_pair(
                name_a, data_a["raw"], spans_a, name_b, data_b["raw"], spans_b, mode=pair_mode
            )
        )
    return "".join(blocks) if rendered > 0 else ""


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
    """Render a plain-paper A4 similarity report as PDF bytes."""
    _ = scan_uuid
    resolved_pairs = pairs if pairs is not None else matrix.all_pairs()
    flagged = [
        p for p in resolved_pairs if bool(p.get("flagged", float(p["score"]) >= threshold))
    ]
    scores = [float(p["score"]) for p in resolved_pairs]
    max_score = max(scores, default=0.0)

    mode_label = (mode or "text_similarity").replace("_", " ")
    sub_parts = [
        f"{len(matrix.names)} files",
        f"{len(flagged)} of {len(resolved_pairs)} pairs flagged (threshold {threshold * 100:.0f}%)",
    ]
    if resolved_pairs:
        sub_parts.append(f"max {max_score * 100:.1f}%")
    sub_parts.append(mode_label)
    if algorithm and algorithm != "auto":
        sub_parts.append(algorithm)
    if created_at:
        sub_parts.append(str(created_at)[:16].replace("T", " "))

    archive = pymupdf.Archive()
    heatmap_html = ""
    if heatmap_png and len(matrix.names) >= 2:
        archive.add(heatmap_png, "heatmap.png")
        heatmap_html = (
            '<h2>Matrix</h2><div class="heatmap-wrap"><img src="heatmap.png" width="390"/></div>'
        )

    is_single_pair = (
        len(matrix.names) == 2
        and len(resolved_pairs) == 1
        and file_data is not None
        and preprocessor is not None
    )
    single_pair_models = None
    if is_single_pair and file_data is not None:
        na, nb = matrix.names[0], matrix.names[1]
        if na in file_data and nb in file_data:
            da, db = file_data[na], file_data[nb]
            sa, sb = matched_spans(
                da["raw"], db["raw"], da["language"], db["language"], preprocessor
            )
            sa = filter_by_word_count(da["raw"], sa, min_match_words)
            sb = filter_by_word_count(db["raw"], sb, min_match_words)
            algo_sc, m_sp = _compute_pair_models(
                da["raw"], da["language"], sa, db["raw"], db["language"], sb, preprocessor
            )
            single_pair_models = (na, da["raw"], sa, nb, db["raw"], sb, algo_sc, m_sp)

    no_flag_note = ""
    if not flagged and single_pair_models is None:
        no_flag_note = (
            f'<p class="muted">No pairs reached the {threshold * 100:.0f}% alert threshold.</p>'
        )

    extra_model_summary = (
        "<h2>Models</h2>" + _model_scores_table_html(single_pair_models[6], threshold)
        if single_pair_models is not None
        else ""
    )

    overview_html = (
        "<html><body>"
        "<h1>Similarity Report</h1>"
        f'<p class="sub">{html.escape(" · ".join(sub_parts))}</p>'
        + _pairs_table_html(resolved_pairs, threshold)
        + extra_model_summary
        + _files_table_html(matrix.names, similarity_indices, source_breakdowns, threshold)
        + heatmap_html
        + no_flag_note
        + "</body></html>"
    )
    overview_pdf = _render_story(overview_html, archive=archive)

    if single_pair_models is not None:
        na, raw_a, sa, nb, raw_b, sb, algo_sc, m_sp = single_pair_models
        cov_pct = float(algo_sc["coverage"] or 0.0) * 100
        cov_html = (
            "<html><body>"
            f"<h1>Coverage ({cov_pct:.1f}%)</h1>"
            f'<p class="sub">{html.escape(na)}  vs  {html.escape(nb)}</p>'
            + _render_doc_pair(na, raw_a, sa, nb, raw_b, sb, mode=mode)
            + "</body></html>"
        )
        cov_bytes = _render_story(cov_html)
        with pymupdf.open("pdf", overview_pdf) as doc:
            with pymupdf.open("pdf", cov_bytes) as cov_doc:
                doc.insert_pdf(cov_doc)
            _append_model_pages(doc, na, raw_a, nb, raw_b, algo_sc, m_sp, mode=mode)
            overview_pdf = doc.tobytes()
    elif flagged and file_data is not None and preprocessor is not None:
        ev_body = _evidence_html(flagged, file_data, preprocessor, min_match_words, mode)
        if ev_body:
            ev_pdf = _render_story(f"<html><body>{ev_body}</body></html>")
            with pymupdf.open("pdf", overview_pdf) as doc, pymupdf.open("pdf", ev_pdf) as tail:
                doc.insert_pdf(tail)
                overview_pdf = doc.tobytes()

    return _stamp_footers(overview_pdf, include_brand=True)
