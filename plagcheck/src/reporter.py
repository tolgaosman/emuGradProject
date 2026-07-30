""" reporter.py — Output artifact generation. """
import html
import io
import os
import re
import tokenize as py_tokenize
from tokenize import TokenError

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .matrix import ComparisonMatrix  # noqa: E402

_PY_KEEP_TYPES = {py_tokenize.NAME, py_tokenize.NUMBER, py_tokenize.STRING}
_KGRAM_K = 5


class ReportGenerator:
    """Generates the CSV matrix, heatmap PNG, and HTML comparison report."""

    def generate(
        self,
        matrix: ComparisonMatrix,
        output_dir: str,
        threshold: float = 0.70,
        file_data: dict | None = None,
        preprocessor=None,
    ) -> dict[str, str]:
        """Write similarity_matrix.csv, similarity_heatmap.png, and the HTML report.

        `file_data` (the same `{name: {"raw", "is_python", ...}}` mapping the
        engine consumed) and `preprocessor` are optional; when both are
        supplied, the HTML report renders side-by-side panes with matched
        5-gram spans highlighted for each flagged pair. Without them it falls
        back to a plain flagged-pairs summary table.
        """
        os.makedirs(output_dir, exist_ok=True)
        return {
            "csv": self._csv(matrix, output_dir),
            "heatmap": self._heatmap(matrix, output_dir, threshold),
            "html": self._html(matrix, output_dir, threshold, file_data, preprocessor),
        }

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

    def _html(
        self,
        m: ComparisonMatrix,
        out: str,
        thr: float,
        file_data: dict | None,
        preprocessor,
    ) -> str:
        flagged = m.get_flagged(thr)
        body = _render_summary(flagged, thr)
        if file_data is not None and preprocessor is not None:
            body += _render_pairs(flagged, file_data, preprocessor)
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


def _spanned_tokens(text: str, is_python: bool, preprocessor) -> list[tuple[str, int, int]]:
    """Return (stemmed_token, start, end) for every surviving token.

    Only tokens that would pass the NLP pipeline's stopword filter are
    kept; each retains its original character span in `text`.
    """
    word_spans = _python_word_spans(text) if is_python else None
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


def matched_spans(
    text_a: str,
    text_b: str,
    is_python_a: bool,
    is_python_b: bool,
    preprocessor,
    k: int = _KGRAM_K,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Find character ranges in `text_a`/`text_b` covered by shared k-grams."""
    tokens_a = _spanned_tokens(text_a, is_python_a, preprocessor)
    tokens_b = _spanned_tokens(text_b, is_python_b, preprocessor)

    def kgram_spans(tokens):
        return [
            (" ".join(t[0] for t in tokens[i : i + k]), tokens[i][1], tokens[i + k - 1][2])
            for i in range(len(tokens) - k + 1)
        ]

    kgrams_a = kgram_spans(tokens_a)
    kgrams_b = kgram_spans(tokens_b)
    set_a = {kg for kg, _, _ in kgrams_a}
    set_b = {kg for kg, _, _ in kgrams_b}

    spans_a = _merge_spans([(s, e) for kg, s, e in kgrams_a if kg in set_b])
    spans_b = _merge_spans([(s, e) for kg, s, e in kgrams_b if kg in set_a])
    return spans_a, spans_b


def _highlight(text: str, spans: list[tuple[int, int]]) -> str:
    """Render `text` as escaped HTML with `spans` wrapped in <mark> tags."""
    if not spans:
        return html.escape(text)
    parts = []
    cursor = 0
    for start, end in spans:
        parts.append(html.escape(text[cursor:start]))
        parts.append(f"<mark>{html.escape(text[start:end])}</mark>")
        cursor = end
    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


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


def _render_pairs(flagged: list[dict], file_data: dict, preprocessor) -> str:
    cards = []
    for pair in flagged:
        name_a, name_b, score = pair["file_a"], pair["file_b"], pair["score"]
        data_a, data_b = file_data.get(name_a), file_data.get(name_b)
        if data_a is None or data_b is None:
            continue
        spans_a, spans_b = matched_spans(
            data_a["raw"], data_b["raw"], data_a["is_python"], data_b["is_python"], preprocessor
        )
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
