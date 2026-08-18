""" reporter.py — Output artifact generation. """
import ast
import copy
import html
import io
import os
import re
import tokenize as py_tokenize
from tokenize import TokenError

import fitz
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .language import CODE_LANGUAGES, blank_comments_and_strings  # noqa: E402
from .matrix import ComparisonMatrix  # noqa: E402
from .models.ast_model import _NormalizerNodeVisitor  # noqa: E402

_PY_KEEP_TYPES = {py_tokenize.NAME, py_tokenize.NUMBER, py_tokenize.STRING}
#: Identifiers/keywords and numeric literals for the non-Python code
#: languages, matched directly against the original source (not
#: comment/string-stripped) so highlighted spans keep exact character
#: offsets — a token matched inside a comment is a rare cosmetic
#: imprecision here, not a scoring error (model scoring uses the
#: comment-aware tokenizer in preprocessor.py instead).
_CODE_WORD_RE = re.compile(r"[A-Za-z_]\w*|\d+\.\d+|\d+")
_KGRAM_K = 5
#: Column at which the PDF renderer hard-wraps source lines. MuPDF's story
#: engine clips (rather than wraps) an unbroken run wider than the line box,
#: so minified input would lose text without this. Sized to the A4 content
#: width at the 7.5pt monospace face used in `_PDF_CSS`.
_PDF_WRAP_COLS = 100


class ReportGenerator:
    """Generates the CSV matrix, heatmap PNG, and HTML comparison report."""

    def generate(
        self,
        matrix: ComparisonMatrix,
        output_dir: str,
        threshold: float = 0.70,
        file_data: dict | None = None,
        preprocessor=None,
        min_match_words: int = 0,
        formats: str = "both",
    ) -> dict[str, str]:
        """Write similarity_matrix.csv, similarity_heatmap.png, and the HTML report.

        `file_data` (the same `{name: {"raw", "language", ...}}` mapping the
        engine consumed) and `preprocessor` are optional; when both are
        supplied, the HTML report renders side-by-side panes with matched
        spans highlighted for each flagged pair. Without them it falls back to
        a plain flagged-pairs summary table.

        `min_match_words` must match what the scan scored with, so the
        highlighting shows exactly the spans that produced the scores.
        `formats` is `csv` | `html` | `both`; the heatmap PNG is always
        written since both report formats reference it. Only the requested
        artifacts are generated, and only those appear in the returned dict.
        """
        os.makedirs(output_dir, exist_ok=True)
        artifacts = {"heatmap": self._heatmap(matrix, output_dir, threshold)}
        if formats in ("csv", "both"):
            artifacts["csv"] = self._csv(matrix, output_dir)
        if formats in ("html", "both"):
            artifacts["html"] = self._html(
                matrix, output_dir, threshold, file_data, preprocessor, min_match_words
            )
        return artifacts

    def _csv(self, m: ComparisonMatrix, out: str) -> str:
        path = os.path.join(out, "similarity_matrix.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write(m.to_csv())
        return path

    def _heatmap(self, m: ComparisonMatrix, out: str, thr: float) -> str:
        path = os.path.join(out, "similarity_heatmap.png")
        with open(path, "wb") as f:
            f.write(self.heatmap_png_bytes(m, thr))
        return path

    def heatmap_png_bytes(self, m: ComparisonMatrix, threshold: float = 0.70) -> bytes:
        """Render the 300 DPI heatmap as PNG bytes, without touching disk."""
        df = pd.DataFrame(m.as_numpy(), index=m.names, columns=m.names)
        n = len(m.names)
        fig, ax = plt.subplots(figsize=(max(6, n), max(5, n)))
        sns.heatmap(
            df, annot=True, fmt=".2f", cmap="YlOrRd", vmin=0, vmax=1, ax=ax, linewidths=0.5
        )
        for i in range(n):
            for j in range(n):
                if i != j and m.get(i, j) >= threshold:
                    ax.add_patch(
                        Rectangle((j, i), 1, 1, fill=False, edgecolor="red", lw=2)
                    )
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png", dpi=300, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    def single_row_heatmap_png_bytes(
        self,
        ref_name: str,
        candidate_names: list[str],
        scores: list[float],
        threshold: float = 0.70,
    ) -> bytes:
        """Render a 1xK similarity heatmap (reference file vs candidates) as PNG bytes."""
        k = len(candidate_names)
        df = pd.DataFrame([scores], index=[ref_name], columns=candidate_names)

        fig_width = max(6, k * 2.2)
        fig_height = 2.8
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))

        sns.heatmap(
            df,
            annot=True,
            fmt=".2f",
            cmap="YlOrRd",
            vmin=0,
            vmax=1,
            ax=ax,
            linewidths=1.0,
            cbar=True,
            annot_kws={"size": 11, "weight": "bold"},
        )

        for j, score in enumerate(scores):
            if score >= threshold:
                ax.add_patch(
                    Rectangle((j, 0), 1, 1, fill=False, edgecolor="red", lw=3)
                )

        plt.yticks(rotation=0, fontsize=10, fontweight="bold")
        plt.xticks(rotation=45, ha="right", fontsize=10)
        plt.title(f"Similarity Matrix (vs {ref_name})", fontsize=12, pad=12, fontweight="bold")

        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png", dpi=300, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    def pair_pdf_bytes(
        self,
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
    ) -> bytes:
        """Render one comparison as a printable PDF, without touching disk.

        Both documents are reproduced in full and stacked (not side by side,
        which would halve the usable width for no gain on long documents),
        each with `spans_a`/`spans_b` highlighted. The spans must be the
        *filtered* ones the scan scored with, so the PDF shows exactly the
        evidence behind the score it prints in its header.

        `score`/`threshold`/`mode`/`algorithm` are optional: when a scan
        record can't be read back, the header simply omits those facts rather
        than stating something the scan never produced.
        """
        meta = []
        if score is not None:
            meta.append(f"Similarity {score * 100:.1f}%")
            if threshold is not None:
                meta.append("Flagged" if score >= threshold else "Below threshold")
        if threshold is not None:
            meta.append(f"threshold {threshold:.2f}")
        if mode:
            meta.append(html.escape(mode))
        if algorithm:
            meta.append(html.escape(algorithm))

        page = _PDF_TEMPLATE.format(
            name_a=html.escape(name_a),
            name_b=html.escape(name_b),
            meta=" &middot; ".join(meta) or "Matched regions highlighted",
            body_a=_segments_to_html(_wrap_segments(_highlight_segments(text_a, spans_a))),
            body_b=_segments_to_html(_wrap_segments(_highlight_segments(text_b, spans_b))),
        )

        story = fitz.Story(html=page, user_css=_PDF_CSS)
        buf = io.BytesIO()
        writer = fitz.DocumentWriter(buf)
        content = fitz.paper_rect("a4") + (36, 36, -36, -36)
        more = 1
        while more:
            device = writer.begin_page(fitz.paper_rect("a4"))
            more, _ = story.place(content)
            story.draw(device)
            writer.end_page()
        writer.close()
        return buf.getvalue()

    def _html(
        self,
        m: ComparisonMatrix,
        out: str,
        thr: float,
        file_data: dict | None,
        preprocessor,
        min_match_words: int = 0,
    ) -> str:
        flagged = m.get_flagged(thr)
        body = _render_summary(flagged, thr)
        if file_data is not None and preprocessor is not None:
            body += _render_pairs(flagged, file_data, preprocessor, min_match_words)
        else:
            body += _render_flat_table(flagged)

        path = os.path.join(out, "comparison_report.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_PAGE_TEMPLATE.format(body=body, flagged_count=len(flagged), threshold=thr))
        return path


# --------------------------------------------------------------------------
# Matched-span detection: reuses the preprocessor's stemmer/stopword set so
# highlighted spans mirror what the winnowing/jaccard/cosine models actually
# compared, but tracks each surviving token's original character offsets
# (which the NLP pipeline discards) so we can highlight the raw source text.
# --------------------------------------------------------------------------


def _line_start_offsets(text: str) -> list[int]:
    """Return the absolute character offset of the start of each line."""
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _python_word_spans(text: str) -> list[tuple[str, int, int]] | None:
    """Return (word, start, end) for each NAME/NUMBER/STRING token.

    Returns None if `text` fails to tokenize.
    """
    try:
        tokens = list(py_tokenize.generate_tokens(io.StringIO(text).readline))
    except (TokenError, IndentationError, SyntaxError):
        return None
    line_starts = _line_start_offsets(text)
    spans = []
    for tok in tokens:
        if tok.type not in _PY_KEEP_TYPES:
            continue
        start = line_starts[tok.start[0] - 1] + tok.start[1]
        end = line_starts[tok.end[0] - 1] + tok.end[1]
        spans.append((tok.string, start, end))
    return spans


def _code_word_spans(text: str, language: str) -> list[tuple[str, int, int]]:
    """Return (word, start, end) for identifier/number tokens in non-Python code.

    Comments and string literals are blanked out first so this yields the
    same token stream `preprocessor._tokenize_code` scores on — otherwise a
    highlighted span could cover comment text that never contributed to the
    score. `blank_comments_and_strings` pads instead of deleting, so the
    offsets still index into the original `text`.
    """
    masked = blank_comments_and_strings(text, language)
    return [(m.group(), m.start(), m.end()) for m in _CODE_WORD_RE.finditer(masked)]


def _spanned_tokens(text: str, language: str, preprocessor) -> list[tuple[str, int, int]]:
    """Return (stemmed_token, start, end) for every surviving token.

    Only tokens that would pass the NLP pipeline's stopword filter are
    kept; each retains its original character span in `text`.
    """
    if language == "python":
        word_spans = _python_word_spans(text)
    elif language in CODE_LANGUAGES:
        word_spans = _code_word_spans(text, language)
    else:
        word_spans = None

    if word_spans is None:
        word_spans = [(m.group(), m.start(), m.end()) for m in re.finditer(r"\w+", text)]

    out = []
    for word, start, end in word_spans:
        stemmed = preprocessor.stemmer.stem(word.lower())
        if stemmed in preprocessor.stop_words:
            continue
        out.append((stemmed, start, end))
    return out


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Collapse overlapping/adjacent (start, end) ranges into contiguous ones."""
    if not spans:
        return []
    ordered = sorted(spans)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def _normalized_def_spans(text: str) -> list[tuple[str, int, int]] | None:
    """Return (normalized_ast_dump, start, end) for each function/class in `text`.

    Each definition is normalized in isolation (on a deep copy, since the
    visitor mutates in place) so its dump depends only on its own structure,
    not on how many identifiers happened to precede it in the file. Two
    definitions that differ *only* by identifier names therefore produce the
    same dump.

    Returns None if `text` isn't parseable Python.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None

    line_starts = _line_start_offsets(text)
    out: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.end_lineno is None:
            continue
        isolated = copy.deepcopy(node)
        _NormalizerNodeVisitor().visit(isolated)
        start = line_starts[node.lineno - 1] + node.col_offset
        end = line_starts[node.end_lineno - 1] + (node.end_col_offset or 0)
        out.append((ast.dump(isolated), start, end))
    return out


def _structural_spans(
    text_a: str, text_b: str
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Char ranges of Python defs/classes that are structurally identical.

    Renaming every variable defeats literal k-gram matching entirely — which
    is the most common way copied code is disguised, and exactly what the AST
    model exists to catch. Reporting those matches as spans keeps that
    evidence *showable*: the score rises only for source the comparison view
    can actually highlight, and a renamed copy is highlighted function by
    function rather than scoring near zero.
    """
    defs_a = _normalized_def_spans(text_a)
    defs_b = _normalized_def_spans(text_b)
    if defs_a is None or defs_b is None:
        return [], []

    dumps_a = {dump for dump, _, _ in defs_a}
    dumps_b = {dump for dump, _, _ in defs_b}
    return (
        _merge_spans([(s, e) for dump, s, e in defs_a if dump in dumps_b]),
        _merge_spans([(s, e) for dump, s, e in defs_b if dump in dumps_a]),
    )


def matched_spans(
    text_a: str,
    text_b: str,
    language_a: str,
    language_b: str,
    preprocessor,
    k: int = _KGRAM_K,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Find character ranges in `text_a`/`text_b` covered by shared content.

    Literal shared k-grams always count. For a Python-to-Python pair,
    structurally identical functions/classes count too (see
    `_structural_spans`) — otherwise a rename-only copy would show no
    evidence at all.
    """
    tokens_a = _spanned_tokens(text_a, language_a, preprocessor)
    tokens_b = _spanned_tokens(text_b, language_b, preprocessor)

    def kgram_spans(tokens):
        return [
            (" ".join(t[0] for t in tokens[i : i + k]), tokens[i][1], tokens[i + k - 1][2])
            for i in range(len(tokens) - k + 1)
        ]

    kgrams_a = kgram_spans(tokens_a)
    kgrams_b = kgram_spans(tokens_b)
    set_a = {kg for kg, _, _ in kgrams_a}
    set_b = {kg for kg, _, _ in kgrams_b}

    raw_a = [(s, e) for kg, s, e in kgrams_a if kg in set_b]
    raw_b = [(s, e) for kg, s, e in kgrams_b if kg in set_a]

    if language_a == "python" and language_b == "python":
        struct_a, struct_b = _structural_spans(text_a, text_b)
        raw_a += struct_a
        raw_b += struct_b

    return _merge_spans(raw_a), _merge_spans(raw_b)


def _highlight_segments(text: str, spans: list[tuple[int, int]]) -> list[tuple[str, bool]]:
    """Split `text` into `(chunk, is_matched)` pairs along `spans`.

    Empty chunks are dropped, so a span starting at offset 0 or ending at the
    last character doesn't introduce blank segments.
    """
    if not spans:
        return [(text, False)] if text else []
    segments: list[tuple[str, bool]] = []
    cursor = 0
    for start, end in spans:
        if start > cursor:
            segments.append((text[cursor:start], False))
        if end > start:
            segments.append((text[start:end], True))
        cursor = end
    if cursor < len(text):
        segments.append((text[cursor:], False))
    return segments


def _wrap_segments(
    segments: list[tuple[str, bool]], cols: int = _PDF_WRAP_COLS
) -> list[tuple[str, bool]]:
    """Hard-wrap `segments` at `cols` columns, preserving match boundaries.

    The PDF renderer lays text out with MuPDF's story engine, which *clips* a
    single unbroken run wider than the line box instead of wrapping it — a
    minified file would silently lose most of its content. Breaking the
    segments rather than the raw text keeps every `<mark>` boundary exactly
    where `matched_spans` put it.
    """
    out: list[tuple[str, bool]] = []
    column = 0
    for chunk, marked in segments:
        buffer: list[str] = []
        for char in chunk:
            if char == "\n":
                buffer.append(char)
                column = 0
                continue
            if column >= cols:
                buffer.append("\n")
                column = 0
            buffer.append(char)
            column += 1
        if buffer:
            out.append(("".join(buffer), marked))
    return out


def _segments_to_html(segments: list[tuple[str, bool]]) -> str:
    """Escape `segments` and wrap the matched ones in <mark> tags."""
    return "".join(
        f"<mark>{html.escape(chunk)}</mark>" if marked else html.escape(chunk)
        for chunk, marked in segments
    )


def _highlight(text: str, spans: list[tuple[int, int]]) -> str:
    """Render `text` as escaped HTML with `spans` wrapped in <mark> tags."""
    return _segments_to_html(_highlight_segments(text, spans))


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------


def _render_summary(flagged: list[dict], thr: float) -> str:
    if not flagged:
        return (
            f'<p class="empty">No pairs met the {thr:.2f} threshold — nothing to review.</p>'
        )
    rows = "".join(
        f'<tr><td>{html.escape(p["file_a"])}</td><td>{html.escape(p["file_b"])}</td>'
        f'<td class="score {"score-high" if p["score"] >= 0.90 else "score-mid"}">'
        f'{p["score"]:.4f}</td></tr>'
        for p in flagged
    )
    return (
        '<table class="summary"><thead><tr><th>File A</th><th>File B</th>'
        f"<th>Score</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _render_flat_table(flagged: list[dict]) -> str:
    if not flagged:
        return ""
    rows = "".join(
        f'<tr><td>{html.escape(p["file_a"])}</td><td>{html.escape(p["file_b"])}</td>'
        f'<td>{p["score"]:.4f}</td><td>Flagged for review</td></tr>'
        for p in flagged
    )
    return (
        '<table class="summary"><thead><tr><th>File A</th><th>File B</th>'
        f"<th>Score</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _render_pairs(
    flagged: list[dict], file_data: dict, preprocessor, min_match_words: int = 0
) -> str:
    # Imported here rather than at module scope: similarity_index imports
    # from this module, so a top-level import would be circular.
    from .similarity_index import _filter_by_word_count

    cards = []
    for pair in flagged:
        name_a, name_b, score = pair["file_a"], pair["file_b"], pair["score"]
        data_a, data_b = file_data.get(name_a), file_data.get(name_b)
        if data_a is None or data_b is None:
            continue
        spans_a, spans_b = matched_spans(
            data_a["raw"], data_b["raw"], data_a["language"], data_b["language"], preprocessor
        )
        # Same filter the scan scored with, so the highlighting can't show
        # matches the score deliberately excluded.
        spans_a = _filter_by_word_count(data_a["raw"], spans_a, min_match_words)
        spans_b = _filter_by_word_count(data_b["raw"], spans_b, min_match_words)
        cards.append(
            _PAIR_TEMPLATE.format(
                name_a=html.escape(name_a),
                name_b=html.escape(name_b),
                score=f"{score:.4f}",
                badge_class="score-high" if score >= 0.90 else "score-mid",
                text_a=_highlight(data_a["raw"], spans_a),
                text_b=_highlight(data_b["raw"], spans_b),
            )
        )
    return "".join(cards)


_PAIR_TEMPLATE = """
<details class="pair" open>
  <summary>
    <span class="pair-names">{name_a} &harr; {name_b}</span>
    <span class="badge {badge_class}">{score}</span>
  </summary>
  <div class="side-by-side">
    <pre class="pane"><code>{text_a}</code></pre>
    <pre class="pane"><code>{text_b}</code></pre>
  </div>
</details>
"""

#: Print stylesheet for `pair_pdf_bytes`. Deliberately light-only — this is
#: paper output, so the dark-mode block in `_PAGE_TEMPLATE` has no meaning
#: here. Kept to the CSS subset MuPDF's story engine actually supports.
_PDF_CSS = """
body { font-family: sans-serif; font-size: 9pt; color: #171717; }
h1 { font-size: 13pt; margin: 0 0 2pt 0; }
.names { font-size: 10pt; margin: 0 0 2pt 0; }
.meta { font-size: 8pt; color: #737373; margin: 0 0 10pt 0; }
h2 {
  font-size: 9pt; color: #737373; margin: 12pt 0 4pt 0;
  border-bottom: 1px solid #e5e5e5; padding-bottom: 2pt;
}
pre {
  font-family: monospace; font-size: 7.5pt; line-height: 1.35;
  white-space: pre-wrap; margin: 0;
}
mark { background-color: #fde68a; }
"""

_PDF_TEMPLATE = """<html><body>
<h1>PlagCheck Similarity Report</h1>
<p class="names">{name_a} &harr; {name_b}</p>
<p class="meta">{meta}</p>
<h2>Reference &mdash; {name_a}</h2>
<pre>{body_a}</pre>
<h2>Compared &mdash; {name_b}</h2>
<pre>{body_b}</pre>
</body></html>
"""

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PlagCheck Similarity Report</title>
<style>
  :root {{
    --bg: #fafafa; --surface: #ffffff; --border: #e5e5e5;
    --text: #171717; --text-muted: #737373;
    --amber: #b45309; --amber-bg: #fef3c7;
    --red: #b91c1c; --red-bg: #fee2e2;
    --mark-bg: #fde68a;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0a0a0a; --surface: #171717; --border: #262626;
      --text: #fafafa; --text-muted: #a3a3a3;
      --amber: #fbbf24; --amber-bg: #451a03;
      --red: #f87171; --red-bg: #450a0a;
      --mark-bg: #78350f;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 2.5rem 1.5rem;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, "Segoe UI", Inter, sans-serif;
    line-height: 1.5;
  }}
  .wrap {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; font-weight: 600; margin: 0 0 0.25rem; letter-spacing: -0.01em; }}
  .subtitle {{ color: var(--text-muted); font-size: 0.9rem; margin: 0 0 2rem; }}
  table.summary {{
    width: 100%; border-collapse: collapse; margin-bottom: 2rem;
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    overflow: hidden;
  }}
  table.summary th, table.summary td {{
    padding: 0.6rem 1rem; text-align: left; border-bottom: 1px solid var(--border);
    font-size: 0.875rem;
  }}
  table.summary th {{ color: var(--text-muted); font-weight: 500; }}
  table.summary tr:last-child td {{ border-bottom: none; }}
  td.score {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
  .score-mid {{ color: var(--amber); }}
  .score-high {{ color: var(--red); }}
  .empty {{ color: var(--text-muted); font-size: 0.9rem; }}
  details.pair {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    margin-bottom: 1rem; overflow: hidden;
    transition: box-shadow 200ms cubic-bezier(0.16, 1, 0.3, 1);
  }}
  details.pair[open] {{ box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  summary {{
    cursor: pointer; padding: 0.85rem 1.1rem; display: flex;
    align-items: center; justify-content: space-between; list-style: none;
    font-size: 0.9rem; font-weight: 500;
  }}
  summary::-webkit-details-marker {{ display: none; }}
  .badge {{
    font-variant-numeric: tabular-nums; font-weight: 600; font-size: 0.8rem;
    padding: 0.15rem 0.55rem; border-radius: 999px;
  }}
  .badge.score-mid {{ background: var(--amber-bg); color: var(--amber); }}
  .badge.score-high {{ background: var(--red-bg); color: var(--red); }}
  .side-by-side {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 1px;
    background: var(--border); border-top: 1px solid var(--border);
  }}
  @media (max-width: 720px) {{ .side-by-side {{ grid-template-columns: 1fr; }} }}
  pre.pane {{
    margin: 0; padding: 1rem; background: var(--surface); overflow-x: auto;
    max-height: 420px; overflow-y: auto;
    font-family: ui-monospace, "SF Mono", Consolas, monospace; font-size: 0.8rem;
    white-space: pre-wrap; word-break: break-word;
  }}
  mark {{ background: var(--mark-bg); color: inherit; border-radius: 3px; padding: 0 1px; }}
</style>
</head>
<body>
  <div class="wrap">
    <h1>Similarity Report</h1>
    <p class="subtitle">Threshold: {threshold:.2f} &middot; Flagged pairs: {flagged_count}</p>
    {body}
  </div>
</body>
</html>
"""
