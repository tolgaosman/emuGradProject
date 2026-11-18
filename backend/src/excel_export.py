"""excel_export.py — Native styled OOXML (.xlsx) workbook generator.

Produces a locale-independent, multi-sheet Excel workbook (`Summary & Pairs`,
`Similarity Matrix`, `File Index`) using Python's standard library (`zipfile` +
XML) with zero external runtime dependencies. Numeric similarity scores are
stored as true IEEE-754 floats formatted with `0.0%`, avoiding the comma/semicolon
delimiter breakage of CSV files on Turkish/European Windows Excel installations.
"""

from __future__ import annotations

import io
import math
import re
import zipfile
from xml.sax.saxutils import escape

from .matrix import ComparisonMatrix

_ILLEGAL_XML_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_NUMFMT_PCT = 164
_NUMFMT_INT = 165

# Fonts: (size_pt, color_rgb, bold)
_FONTS: tuple[tuple[float, str, bool], ...] = (
    (10.0, "FF18181B", False),  # 0: body regular
    (13.5, "FFFFFFFF", True),   # 1: banner title
    (9.5, "FFD4D4D8", False),   # 2: banner subtitle
    (10.0, "FFFFFFFF", True),   # 3: table header
    (10.0, "FF18181B", True),   # 4: body bold
    (9.5, "FF71717A", False),   # 5: muted label
    (10.0, "FF991B1B", True),   # 6: high-risk red bold
    (10.0, "FF92400E", True),   # 7: moderate-risk amber bold
    (10.0, "FF065F46", True),   # 8: clear emerald bold
)

# Fills: index 0 and 1 are reserved by ECMA-376 (`none` and `gray125`).
_SOLID_FILLS: tuple[str, ...] = (
    "FF18181B",  # 2: dark charcoal banner
    "FF27272A",  # 3: slate table header
    "FFF4F4F5",  # 4: soft neutral surface / zebra
    "FFFFFFFF",  # 5: crisp white cell
    "FFFEE2E2",  # 6: high-risk coral tint
    "FFFEF3C7",  # 7: moderate-risk amber tint
    "FFFEFCE8",  # 8: low-overlap warm tint
    "FFECFDF5",  # 9: clear emerald tint
    "FFE4E4E7",  # 10: matrix diagonal muted gray
)

# Cell XFs: (num_fmt, font_id, fill_id, border_id, h_align, v_align, wrap)
_XFS: dict[str, tuple[int, int, int, int, str, str, bool]] = {
    "default":       (0,           0, 0,  0, "left",   "center", False),
    "banner_title":  (0,           1, 2,  0, "left",   "center", False),
    "banner_sub":    (0,           2, 2,  2, "left",   "center", False),
    "kpi_label":     (0,           5, 4,  1, "left",   "center", False),
    "kpi_text":      (0,           4, 5,  1, "right",  "center", False),
    "kpi_int":       (_NUMFMT_INT, 4, 5,  1, "right",  "center", False),
    "kpi_pct":       (_NUMFMT_PCT, 4, 5,  1, "right",  "center", False),
    "kpi_pct_alert": (_NUMFMT_PCT, 6, 6,  1, "right",  "center", False),
    "th_left":       (0,           3, 3,  2, "left",   "center", True),
    "th_center":     (0,           3, 3,  2, "center", "center", True),
    "td_idx":        (_NUMFMT_INT, 5, 5,  1, "center", "center", False),
    "td_idx_alt":    (_NUMFMT_INT, 5, 4,  1, "center", "center", False),
    "td_text":       (0,           0, 5,  1, "left",   "center", False),
    "td_text_alt":   (0,           0, 4,  1, "left",   "center", False),
    "td_bold":       (0,           4, 4,  1, "left",   "center", False),
    "td_int":        (_NUMFMT_INT, 0, 5,  1, "center", "center", False),
    "td_int_alt":    (_NUMFMT_INT, 0, 4,  1, "center", "center", False),
    "pct_high":      (_NUMFMT_PCT, 6, 6,  1, "center", "center", False),
    "pct_high_flag": (_NUMFMT_PCT, 6, 6,  3, "center", "center", False),
    "pct_mid":       (_NUMFMT_PCT, 7, 7,  1, "center", "center", False),
    "pct_mid_flag":  (_NUMFMT_PCT, 7, 7,  3, "center", "center", False),
    "pct_low":       (_NUMFMT_PCT, 0, 8,  1, "center", "center", False),
    "pct_clear":     (_NUMFMT_PCT, 0, 5,  1, "center", "center", False),
    "pct_clear_alt": (_NUMFMT_PCT, 0, 4,  1, "center", "center", False),
    "pct_diag":      (0,           5, 10, 1, "center", "center", False),
    "badge_flag":    (0,           6, 6,  1, "center", "center", False),
    "badge_mid":     (0,           7, 7,  1, "center", "center", False),
    "badge_clear":   (0,           8, 9,  1, "center", "center", False),
    "empty_note":    (0,           5, 4,  1, "center", "center", False),
}

_STYLE_IDS: dict[str, int] = {name: idx for idx, name in enumerate(_XFS)}


def _clean_xml_text(value: str) -> str:
    return _ILLEGAL_XML_RE.sub("", value)


def _col_letter(col_idx_1based: int) -> str:
    chars: list[str] = []
    n = col_idx_1based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(65 + rem))
    return "".join(reversed(chars))


def _cell_ref(col_1based: int, row_1based: int) -> str:
    return f"{_col_letter(col_1based)}{row_1based}"


class _SharedStrings:
    def __init__(self) -> None:
        self._index: dict[str, int] = {}
        self._items: list[str] = []

    def intern(self, text: str) -> int:
        cleaned = _clean_xml_text(text)
        existing = self._index.get(cleaned)
        if existing is not None:
            return existing
        idx = len(self._items)
        self._index[cleaned] = idx
        self._items.append(cleaned)
        return idx

    def to_xml(self) -> str:
        n = len(self._items)
        nodes = "".join(
            f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in self._items
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'count="{n}" uniqueCount="{n}">{nodes}</sst>'
        )


class _SheetBuilder:
    def __init__(self, strings: _SharedStrings) -> None:
        self._strings = strings
        self._rows: dict[int, tuple[float, list[tuple[int, str]]]] = {}
        self._cols: list[tuple[int, int, float]] = []
        self._merges: list[str] = []
        self._freeze: tuple[int, int] | None = None
        self._autofilter: str | None = None

    def set_col_width(self, col_min: int, col_max: int, width: float) -> None:
        self._cols.append((col_min, col_max, round(width, 2)))

    def freeze(self, x_split: int, y_split: int) -> None:
        self._freeze = (x_split, y_split)

    def set_autofilter(self, ref: str) -> None:
        self._autofilter = ref

    def _row_cells(self, row: int, height: float = 21.0) -> list[tuple[int, str]]:
        entry = self._rows.get(row)
        if entry is None:
            cells: list[tuple[int, str]] = []
            self._rows[row] = (height, cells)
            return cells
        if height > entry[0]:
            self._rows[row] = (height, entry[1])
        return entry[1]

    def put_str(self, col: int, row: int, text: str, style: str, height: float = 21.0) -> None:
        sid = _STYLE_IDS[style]
        str_idx = self._strings.intern(text)
        ref = _cell_ref(col, row)
        cell_xml = f'<c r="{ref}" s="{sid}" t="s"><v>{str_idx}</v></c>'
        self._row_cells(row, height).append((col, cell_xml))

    def put_num(
        self, col: int, row: int, num: float | int, style: str, height: float = 21.0
    ) -> None:
        sid = _STYLE_IDS[style]
        ref = _cell_ref(col, row)
        val = 0.0 if isinstance(num, float) and not math.isfinite(num) else num
        self._row_cells(row, height).append((col, f'<c r="{ref}" s="{sid}"><v>{val}</v></c>'))

    def put_blank(self, col: int, row: int, style: str, height: float = 21.0) -> None:
        sid = _STYLE_IDS[style]
        ref = _cell_ref(col, row)
        self._row_cells(row, height).append((col, f'<c r="{ref}" s="{sid}"/>'))

    def merge_banner(self, row: int, max_col: int, text: str, style: str, height: float) -> None:
        self.put_str(1, row, text, style, height=height)
        for col in range(2, max_col + 1):
            self.put_blank(col, row, style, height=height)
        if max_col > 1:
            self._merges.append(f"A{row}:{_col_letter(max_col)}{row}")

    def to_xml(self, active: bool = False) -> str:
        tab_sel = ' tabSelected="1"' if active else ""
        pane_xml = ""
        if self._freeze is not None:
            xs, ys = self._freeze
            top_left = _cell_ref(xs + 1, ys + 1)
            active_pane = "bottomRight" if xs and ys else ("bottomLeft" if ys else "topRight")
            x_attr = f' xSplit="{xs}"' if xs else ""
            y_attr = f' ySplit="{ys}"' if ys else ""
            pane_xml = (
                f'<pane{x_attr}{y_attr} topLeftCell="{top_left}" '
                f'activePane="{active_pane}" state="frozen"/>'
            )

        cols_xml = ""
        if self._cols:
            items = "".join(
                f'<col min="{c0}" max="{c1}" width="{w}" customWidth="1"/>'
                for c0, c1, w in self._cols
            )
            cols_xml = f"<cols>{items}</cols>"

        rows_out: list[str] = []
        for r_num in sorted(self._rows):
            height, cells = self._rows[r_num]
            ordered = "".join(xml for _, xml in sorted(cells, key=lambda item: item[0]))
            rows_out.append(f'<row r="{r_num}" ht="{height}" customHeight="1">{ordered}</row>')

        af_xml = f'<autoFilter ref="{self._autofilter}"/>' if self._autofilter else ""
        merge_xml = ""
        if self._merges:
            m_nodes = "".join(f'<mergeCell ref="{ref}"/>' for ref in self._merges)
            merge_xml = f'<mergeCells count="{len(self._merges)}">{m_nodes}</mergeCells>'

        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetViews><sheetView{tab_sel} workbookViewId="0" showGridLines="1">'
            f"{pane_xml}</sheetView></sheetViews>"
            '<sheetFormatPr defaultRowHeight="21"/>'
            f"{cols_xml}"
            f'<sheetData>{"".join(rows_out)}</sheetData>'
            f"{af_xml}{merge_xml}"
            '<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>'
            "</worksheet>"
        )


def _styles_xml() -> str:
    fonts_xml = "".join(
        f"<font>{'<b/>' if bold else ''}<sz val=\"{sz}\"/>"
        f'<color rgb="{rgb}"/><name val="Segoe UI"/><family val="2"/></font>'
        for sz, rgb, bold in _FONTS
    )
    fills_xml = (
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        + "".join(
            f'<fill><patternFill patternType="solid"><fgColor rgb="{rgb}"/>'
            '<bgColor indexed="64"/></patternFill></fill>'
            for rgb in _SOLID_FILLS
        )
    )
    borders_xml = (
        "<border><left/><right/><top/><bottom/><diagonal/></border>"
        "<border>"
        '<left style="thin"><color rgb="FFE4E4E7"/></left>'
        '<right style="thin"><color rgb="FFE4E4E7"/></right>'
        '<top style="thin"><color rgb="FFE4E4E7"/></top>'
        '<bottom style="thin"><color rgb="FFE4E4E7"/></bottom>'
        "<diagonal/></border>"
        "<border>"
        '<left style="thin"><color rgb="FF3F3F46"/></left>'
        '<right style="thin"><color rgb="FF3F3F46"/></right>'
        '<top style="thin"><color rgb="FF27272A"/></top>'
        '<bottom style="medium"><color rgb="FFF5B921"/></bottom>'
        "<diagonal/></border>"
        "<border>"
        '<left style="medium"><color rgb="FFDC2626"/></left>'
        '<right style="medium"><color rgb="FFDC2626"/></right>'
        '<top style="medium"><color rgb="FFDC2626"/></top>'
        '<bottom style="medium"><color rgb="FFDC2626"/></bottom>'
        "<diagonal/></border>"
    )
    xfs_xml = "".join(
        f'<xf numFmtId="{nf}" fontId="{fo}" fillId="{fi}" borderId="{bo}" xfId="0"'
        f'{" applyNumberFormat=\"1\"" if nf else ""} applyFont="1" applyFill="1" '
        f'applyBorder="1" applyAlignment="1">'
        f'<alignment horizontal="{ha}" vertical="{va}"{" wrapText=\"1\"" if wrap else ""}/></xf>'
        for nf, fo, fi, bo, ha, va, wrap in _XFS.values()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<numFmts count="2">'
        f'<numFmt numFmtId="{_NUMFMT_PCT}" formatCode="0.0%"/>'
        f'<numFmt numFmtId="{_NUMFMT_INT}" formatCode="#,##0"/>'
        "</numFmts>"
        f'<fonts count="{len(_FONTS)}">{fonts_xml}</fonts>'
        f'<fills count="{2 + len(_SOLID_FILLS)}">{fills_xml}</fills>'
        f'<borders count="4">{borders_xml}</borders>'
        '<cellStyleXfs count="1">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        f'<cellXfs count="{len(_XFS)}">{xfs_xml}</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '<dxfs count="0"/>'
        '<tableStyles count="0" defaultTableStyle="TableStyleMedium2" '
        'defaultPivotStyle="PivotStyleLight16"/>'
        "</styleSheet>"
    )


def _score_pct_style(
    score: float, threshold: float, alt: bool = False, matrix_cell: bool = False
) -> str:
    flagged = score >= threshold
    if score >= 0.70:
        return "pct_high_flag" if (flagged and matrix_cell) else "pct_high"
    if flagged or score >= 0.40:
        return "pct_mid_flag" if (flagged and matrix_cell) else "pct_mid"
    if score >= 0.15:
        return "pct_low"
    return "pct_clear_alt" if alt else "pct_clear"


def _risk_label(score: float, threshold: float) -> tuple[str, str]:
    if score >= 0.70:
        return "High", "badge_flag"
    if score >= threshold or score >= 0.40:
        return "Moderate", "badge_mid"
    return "Low", "badge_clear"


def _build_summary_pairs_sheet(
    strings: _SharedStrings,
    names: list[str],
    pairs: list[dict],
    threshold: float,
    mode: str,
    algorithm: str,
    min_match_words: int,
    scan_uuid: str | None,
    created_at: str | None,
) -> _SheetBuilder:
    sh = _SheetBuilder(strings)
    meta_parts = [f"Mode: {mode}", f"Engine: {algorithm}", f"Threshold: {threshold * 100:.0f}%"]
    if scan_uuid:
        meta_parts.insert(0, f"Scan {scan_uuid[:8]}")
    if created_at:
        meta_parts.append(str(created_at)[:19].replace("T", " "))

    sh.merge_banner(1, 7, "PlagCheck — Similarity Analysis Report", "banner_title", 30.0)
    sh.merge_banner(2, 7, "  ·  ".join(meta_parts), "banner_sub", 20.0)

    scores = [float(p["score"]) for p in pairs]
    flagged_count = sum(1 for p in pairs if p.get("flagged", p["score"] >= threshold))
    max_score = max(scores, default=0.0)
    mean_score = sum(scores) / len(scores) if scores else 0.0

    # 2-row KPI & configuration block (Rows 4-5)
    sh.put_str(1, 4, "Files", "kpi_label", 22.0)
    sh.put_num(2, 4, len(names), "kpi_int", 22.0)
    sh.put_str(3, 4, "Flagged / Total Pairs", "kpi_label", 22.0)
    sh.put_str(4, 4, f"{flagged_count} / {len(pairs)}", "kpi_text", 22.0)
    sh.put_str(5, 4, "Highest Similarity", "kpi_label", 22.0)
    sh.put_num(6, 4, max_score, "kpi_pct_alert" if max_score >= threshold else "kpi_pct", 22.0)
    sh.put_blank(7, 4, "kpi_label", 22.0)

    sh.put_str(1, 5, "Threshold", "kpi_label", 22.0)
    sh.put_num(2, 5, threshold, "kpi_pct", 22.0)
    sh.put_str(3, 5, "Mean Similarity", "kpi_label", 22.0)
    sh.put_num(4, 5, mean_score, "kpi_pct", 22.0)
    sh.put_str(5, 5, "Min Match Filter", "kpi_label", 22.0)
    sh.put_str(6, 5, f"{min_match_words} words", "kpi_text", 22.0)
    sh.put_blank(7, 5, "kpi_label", 22.0)

    headers = [
        ("#", "th_center"),
        ("Document A", "th_left"),
        ("Document B", "th_left"),
        ("Similarity", "th_center"),
        ("Matched 5-grams", "th_center"),
        ("Risk Band", "th_center"),
        ("Status", "th_center"),
    ]
    for col_idx, (title, h_style) in enumerate(headers, start=1):
        sh.put_str(col_idx, 7, title, h_style, height=26.0)
    sh.freeze(0, 7)

    ordered = sorted(pairs, key=lambda item: float(item["score"]), reverse=True)
    if not ordered:
        sh.merge_banner(8, 7, "No document pairs to compare in this scan.", "empty_note", 24.0)
    else:
        for idx, pair in enumerate(ordered, start=1):
            row = 7 + idx
            alt = idx % 2 == 0
            score = float(pair["score"])
            flagged = bool(pair.get("flagged", score >= threshold))
            risk_txt, risk_style = _risk_label(score, threshold)
            sh.put_num(1, row, idx, "td_idx_alt" if alt else "td_idx", 22.0)
            sh.put_str(2, row, str(pair["file_a"]), "td_text_alt" if alt else "td_text", 22.0)
            sh.put_str(3, row, str(pair["file_b"]), "td_text_alt" if alt else "td_text", 22.0)
            sh.put_num(4, row, score, _score_pct_style(score, threshold, alt=alt), 22.0)
            kgrams = pair.get("matched_kgrams")
            if isinstance(kgrams, int):
                sh.put_num(5, row, kgrams, "td_int_alt" if alt else "td_int", 22.0)
            else:
                sh.put_str(5, row, "—", "td_int_alt" if alt else "td_int", 22.0)
            sh.put_str(6, row, risk_txt, risk_style, 22.0)
            sh.put_str(
                7,
                row,
                "FLAGGED" if flagged else "Clear",
                "badge_flag" if flagged else "badge_clear",
                22.0,
            )
        sh.set_autofilter(f"A7:G{7 + len(ordered)}")

    max_name_a = max((len(str(p["file_a"])) for p in ordered), default=18)
    max_name_b = max((len(str(p["file_b"])) for p in ordered), default=18)
    sh.set_col_width(1, 1, 8)
    sh.set_col_width(2, 2, min(48, max(24, max_name_a + 5)))
    sh.set_col_width(3, 3, min(48, max(24, max_name_b + 5)))
    sh.set_col_width(4, 4, 16)
    sh.set_col_width(5, 5, 18)
    sh.set_col_width(6, 6, 15)
    sh.set_col_width(7, 7, 15)
    return sh


def _build_matrix_sheet(
    strings: _SharedStrings, matrix: ComparisonMatrix, threshold: float
) -> _SheetBuilder:
    sh = _SheetBuilder(strings)
    names = matrix.names
    n = len(names)
    total_cols = max(3, n + 1)

    sh.merge_banner(
        1,
        total_cols,
        f"Pairwise Similarity Matrix ({n} × {n})",
        "banner_title",
        28.0,
    )
    sh.merge_banner(
        2,
        total_cols,
        f"Off-diagonal cells above {threshold * 100:.0f}% threshold are highlighted in red/amber.",
        "banner_sub",
        19.0,
    )

    sh.put_str(1, 4, "Document", "th_left", height=34.0)
    for j, name in enumerate(names, start=2):
        sh.put_str(j, 4, name, "th_center", height=34.0)
    sh.freeze(1, 4)

    for i, row_name in enumerate(names):
        r_num = 5 + i
        sh.put_str(1, r_num, row_name, "td_bold", height=23.0)
        for j in range(n):
            col = 2 + j
            if i == j:
                sh.put_str(col, r_num, "—", "pct_diag", height=23.0)
            else:
                score = float(matrix.get(i, j))
                sh.put_num(
                    col,
                    r_num,
                    score,
                    _score_pct_style(score, threshold, matrix_cell=True),
                    height=23.0,
                )

    first_w = min(46, max(22, max((len(nm) for nm in names), default=14) + 5))
    sh.set_col_width(1, 1, first_w)
    for j, name in enumerate(names, start=2):
        sh.set_col_width(j, j, min(26, max(14, len(name) * 0.65 + 6)))
    return sh


def _build_files_sheet(
    strings: _SharedStrings,
    names: list[str],
    similarity_indices: dict[str, float] | None,
    source_breakdowns: dict[str, list[dict]] | None,
    threshold: float,
) -> _SheetBuilder:
    sh = _SheetBuilder(strings)
    indices = similarity_indices or {}
    breakdowns = source_breakdowns or {}

    sh.merge_banner(1, 6, "Per-Document Similarity Index", "banner_title", 28.0)
    sh.merge_banner(
        2,
        6,
        "Asymmetric percentage of each document's text matched against any other submission.",
        "banner_sub",
        19.0,
    )

    headers = [
        ("#", "th_center"),
        ("Document", "th_left"),
        ("Similarity Index", "th_center"),
        ("Primary Source", "th_left"),
        ("Primary Overlap", "th_center"),
        ("Status", "th_center"),
    ]
    for col_idx, (title, style) in enumerate(headers, start=1):
        sh.put_str(col_idx, 4, title, style, height=26.0)
    sh.freeze(0, 4)

    ranked_names = sorted(names, key=lambda nm: float(indices.get(nm, 0.0)), reverse=True)
    for idx, name in enumerate(ranked_names, start=1):
        row = 4 + idx
        alt = idx % 2 == 0
        sim_idx = float(indices.get(name, 0.0))
        sources = breakdowns.get(name) or []
        top_src = str(sources[0]["source"]) if sources else "—"
        raw_contrib = (
            sources[0].get("contribution", sources[0].get("share")) if sources else None
        )
        top_share = float(raw_contrib) if raw_contrib is not None else None
        flagged = sim_idx >= threshold

        sh.put_num(1, row, idx, "td_idx_alt" if alt else "td_idx", 22.0)
        sh.put_str(2, row, name, "td_text_alt" if alt else "td_text", 22.0)
        sh.put_num(3, row, sim_idx, _score_pct_style(sim_idx, threshold, alt=alt), 22.0)
        sh.put_str(4, row, top_src, "td_text_alt" if alt else "td_text", 22.0)
        if top_share is not None:
            sh.put_num(5, row, top_share, _score_pct_style(top_share, threshold, alt=alt), 22.0)
        else:
            sh.put_str(5, row, "—", "td_int_alt" if alt else "td_int", 22.0)
        sh.put_str(
            6,
            row,
            "Needs Review" if flagged else "Clean",
            "badge_flag" if flagged else "badge_clear",
            22.0,
        )

    max_doc = max((len(nm) for nm in names), default=18)
    sh.set_col_width(1, 1, 8)
    sh.set_col_width(2, 2, min(48, max(24, max_doc + 5)))
    sh.set_col_width(3, 3, 18)
    sh.set_col_width(4, 4, min(48, max(24, max_doc + 5)))
    sh.set_col_width(5, 5, 17)
    sh.set_col_width(6, 6, 16)
    return sh


def build_workbook_bytes(
    matrix: ComparisonMatrix,
    threshold: float = 0.70,
    pairs: list[dict] | None = None,
    mode: str = "text_similarity",
    algorithm: str | None = None,
    min_match_words: int = 8,
    similarity_indices: dict[str, float] | None = None,
    source_breakdowns: dict[str, list[dict]] | None = None,
    scan_uuid: str | None = None,
    created_at: str | None = None,
) -> bytes:
    """Serialize a 3-sheet styled `.xlsx` report workbook into memory."""
    strings = _SharedStrings()
    resolved_pairs = pairs if pairs is not None else matrix.all_pairs()
    algo_label = algorithm or "auto"

    sheet1 = _build_summary_pairs_sheet(
        strings,
        matrix.names,
        resolved_pairs,
        threshold,
        mode,
        algo_label,
        min_match_words,
        scan_uuid,
        created_at,
    )
    sheet2 = _build_matrix_sheet(strings, matrix, threshold)
    sheet3 = _build_files_sheet(
        strings, matrix.names, similarity_indices, source_breakdowns, threshold
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet3.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="Summary &amp; Pairs" sheetId="1" r:id="rId1"/>'
        '<sheet name="Similarity Matrix" sheetId="2" r:id="rId2"/>'
        '<sheet name="File Index" sheetId="3" r:id="rId3"/>'
        "</sheets>"
        "</workbook>"
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet2.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet3.xml"/>'
        '<Relationship Id="rId4" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        '<Relationship Id="rId5" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
        'Target="sharedStrings.xml"/>'
        "</Relationships>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/styles.xml", _styles_xml())
        zf.writestr("xl/worksheets/sheet1.xml", sheet1.to_xml(active=True))
        zf.writestr("xl/worksheets/sheet2.xml", sheet2.to_xml())
        zf.writestr("xl/worksheets/sheet3.xml", sheet3.to_xml())
        zf.writestr("xl/sharedStrings.xml", strings.to_xml())
    return buf.getvalue()
