"""excel_export.py — Clean, tabular `.xlsx` export using stdlib `zipfile` + XML."""

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

# Fonts: (size_pt, rgb, bold) — restrained monochrome + muted crimson for flagged items.
_FONTS: tuple[tuple[float, str, bool], ...] = (
    (10.0, "FF18181B", False),  # 0: regular ink
    (10.0, "FF18181B", True),   # 1: header / row label bold
    (10.0, "FF71717A", False),  # 2: muted secondary / dash
    (10.0, "FF991B1B", True),   # 3: flagged crimson bold
    (10.0, "FF92400E", False),  # 4: moderate warm amber
)

# Fills (0=none and 1=gray125 are required by ECMA-376).
_SOLID_FILLS: tuple[str, ...] = (
    "FFF4F4F5",  # 2: subtle stone table header / row header
    "FFFFFFFF",  # 3: plain white cell
    "FFFDF2F2",  # 4: soft muted rose for flagged scores
    "FFFEFCE8",  # 5: very soft warm tint for moderate overlap
    "FFFAFAFA",  # 6: subtle diagonal cell
)

# Every style is horizontally and vertically centered (`center`, `center`).
# Tuple: (num_fmt, font_id, fill_id, border_id, wrap)
_XFS: dict[str, tuple[int, int, int, int, bool]] = {
    "default":   (0,           0, 0, 0, False),
    "th":        (0,           1, 2, 2, True),
    "row_head":  (0,           1, 2, 1, False),
    "text":      (0,           0, 3, 1, False),
    "muted":     (0,           2, 3, 1, False),
    "diag":      (0,           2, 6, 1, False),
    "int":       (_NUMFMT_INT, 0, 3, 1, False),
    "pct":       (_NUMFMT_PCT, 0, 3, 1, False),
    "pct_warm":  (_NUMFMT_PCT, 4, 5, 1, False),
    "pct_flag":  (_NUMFMT_PCT, 3, 4, 1, False),
    "flag_yes":  (0,           3, 4, 1, False),
}

_STYLE_IDS: dict[str, int] = {name: idx for idx, name in enumerate(_XFS)}


def _col_letter(col_1based: int) -> str:
    chars: list[str] = []
    n = col_1based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(65 + rem))
    return "".join(reversed(chars))


def _cell_ref(col: int, row: int) -> str:
    return f"{_col_letter(col)}{row}"


class _SharedStrings:
    def __init__(self) -> None:
        self._index: dict[str, int] = {}
        self._items: list[str] = []

    def intern(self, text: str) -> int:
        cleaned = _ILLEGAL_XML_RE.sub("", text)
        idx = self._index.get(cleaned)
        if idx is None:
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


class _Sheet:
    def __init__(self, strings: _SharedStrings) -> None:
        self._strings = strings
        self._rows: dict[int, tuple[float, list[tuple[int, str]]]] = {}
        self._cols: list[tuple[int, int, float]] = []
        self._freeze: tuple[int, int] | None = None
        self._autofilter: str | None = None

    def col_width(self, c_min: int, c_max: int, width: float) -> None:
        self._cols.append((c_min, c_max, round(width, 2)))

    def freeze(self, x_split: int, y_split: int) -> None:
        self._freeze = (x_split, y_split)

    def autofilter(self, ref: str) -> None:
        self._autofilter = ref

    def _row(self, row: int, height: float) -> list[tuple[int, str]]:
        entry = self._rows.get(row)
        if entry is None:
            cells: list[tuple[int, str]] = []
            self._rows[row] = (height, cells)
            return cells
        if height > entry[0]:
            self._rows[row] = (height, entry[1])
        return entry[1]

    def put_str(
        self, col: int, row: int, text: str, style: str = "text", height: float = 21.0
    ) -> None:
        sid = _STYLE_IDS[style]
        idx = self._strings.intern(text)
        ref = _cell_ref(col, row)
        self._row(row, height).append((col, f'<c r="{ref}" s="{sid}" t="s"><v>{idx}</v></c>'))

    def put_num(
        self, col: int, row: int, val: float | int, style: str = "int", height: float = 21.0
    ) -> None:
        sid = _STYLE_IDS[style]
        ref = _cell_ref(col, row)
        clean = 0.0 if isinstance(val, float) and not math.isfinite(val) else val
        self._row(row, height).append((col, f'<c r="{ref}" s="{sid}"><v>{clean}</v></c>'))

    def to_xml(self, active: bool = False) -> str:
        sel = ' tabSelected="1"' if active else ""
        pane = ""
        if self._freeze is not None:
            xs, ys = self._freeze
            tl = _cell_ref(xs + 1, ys + 1)
            ap = "bottomRight" if xs and ys else ("bottomLeft" if ys else "topRight")
            xa = f' xSplit="{xs}"' if xs else ""
            ya = f' ySplit="{ys}"' if ys else ""
            pane = f'<pane{xa}{ya} topLeftCell="{tl}" activePane="{ap}" state="frozen"/>'

        cols = ""
        if self._cols:
            items = "".join(
                f'<col min="{c0}" max="{c1}" width="{w}" customWidth="1"/>'
                for c0, c1, w in self._cols
            )
            cols = f"<cols>{items}</cols>"

        rows = []
        for r_idx in sorted(self._rows):
            ht, cells = self._rows[r_idx]
            inner = "".join(xml for _, xml in sorted(cells, key=lambda x: x[0]))
            rows.append(f'<row r="{r_idx}" ht="{ht}" customHeight="1">{inner}</row>')

        af = f'<autoFilter ref="{self._autofilter}"/>' if self._autofilter else ""
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetViews><sheetView{sel} workbookViewId="0" showGridLines="1">'
            f"{pane}</sheetView></sheetViews>"
            '<sheetFormatPr defaultRowHeight="21"/>'
            f"{cols}<sheetData>{''.join(rows)}</sheetData>{af}"
            '<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>'
            "</worksheet>"
        )


def _styles_xml() -> str:
    fonts = "".join(
        f"<font>{'<b/>' if bold else ''}<sz val=\"{sz}\"/>"
        f'<color rgb="{rgb}"/><name val="Calibri"/><family val="2"/></font>'
        for sz, rgb, bold in _FONTS
    )
    fills = (
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        + "".join(
            f'<fill><patternFill patternType="solid"><fgColor rgb="{rgb}"/>'
            '<bgColor indexed="64"/></patternFill></fill>'
            for rgb in _SOLID_FILLS
        )
    )
    borders = (
        "<border><left/><right/><top/><bottom/><diagonal/></border>"
        "<border>"
        '<left style="thin"><color rgb="FFE4E4E7"/></left>'
        '<right style="thin"><color rgb="FFE4E4E7"/></right>'
        '<top style="thin"><color rgb="FFE4E4E7"/></top>'
        '<bottom style="thin"><color rgb="FFE4E4E7"/></bottom>'
        "<diagonal/></border>"
        "<border>"
        '<left style="thin"><color rgb="FFD4D4D8"/></left>'
        '<right style="thin"><color rgb="FFD4D4D8"/></right>'
        '<top style="thin"><color rgb="FFD4D4D8"/></top>'
        '<bottom style="medium"><color rgb="FFA1A1AA"/></bottom>'
        "<diagonal/></border>"
    )
    xfs = "".join(
        f'<xf numFmtId="{nf}" fontId="{fo}" fillId="{fi}" borderId="{bo}" xfId="0"'
        f'{" applyNumberFormat=\"1\"" if nf else ""} applyFont="1" applyFill="1" '
        f'applyBorder="1" applyAlignment="1">'
        f'<alignment horizontal="center" vertical="center"'
        f'{" wrapText=\"1\"" if wrap else ""}/></xf>'
        for nf, fo, fi, bo, wrap in _XFS.values()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<numFmts count="2">'
        f'<numFmt numFmtId="{_NUMFMT_PCT}" formatCode="0.0%"/>'
        f'<numFmt numFmtId="{_NUMFMT_INT}" formatCode="#,##0"/>'
        "</numFmts>"
        f'<fonts count="{len(_FONTS)}">{fonts}</fonts>'
        f'<fills count="{2 + len(_SOLID_FILLS)}">{fills}</fills>'
        f'<borders count="3">{borders}</borders>'
        '<cellStyleXfs count="1">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        f'<cellXfs count="{len(_XFS)}">{xfs}</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '<dxfs count="0"/>'
        '<tableStyles count="0" defaultTableStyle="TableStyleMedium2" '
        'defaultPivotStyle="PivotStyleLight16"/>'
        "</styleSheet>"
    )


def _pct_style(score: float, threshold: float) -> str:
    if score >= threshold:
        return "pct_flag"
    if score >= 0.40:
        return "pct_warm"
    return "pct"


def _pairs_sheet(strings: _SharedStrings, pairs: list[dict], threshold: float) -> _Sheet:
    sh = _Sheet(strings)
    for col, title in enumerate(
        ("Reference File", "File to be Checked", "Similarity", "Shared 5-grams", "Review"),
        start=1,
    ):
        sh.put_str(col, 1, title, "th", height=25.0)
    sh.freeze(0, 1)

    ordered = sorted(pairs, key=lambda item: float(item["score"]), reverse=True)
    if not ordered:
        sh.put_str(1, 2, "—", "muted")
        sh.put_str(2, 2, "—", "muted")
        sh.put_num(3, 2, 0.0, "pct")
        sh.put_str(4, 2, "—", "muted")
        sh.put_str(5, 2, "—", "muted")
    else:
        for idx, pair in enumerate(ordered, start=2):
            score = float(pair["score"])
            flagged = bool(pair.get("flagged", score >= threshold))
            sh.put_str(1, idx, str(pair["file_a"]), "text")
            sh.put_str(2, idx, str(pair["file_b"]), "text")
            sh.put_num(3, idx, score, _pct_style(score, threshold))
            kgrams = pair.get("matched_kgrams")
            if isinstance(kgrams, int):
                sh.put_num(4, idx, kgrams, "int")
            else:
                sh.put_str(4, idx, "—", "muted")
            sh.put_str(5, idx, "Flagged" if flagged else "—", "flag_yes" if flagged else "muted")
        sh.autofilter(f"A1:E{1 + len(ordered)}")

    w_a = max((len(str(p["file_a"])) for p in ordered), default=16)
    w_b = max((len(str(p["file_b"])) for p in ordered), default=16)
    sh.col_width(1, 1, min(48, max(22, w_a + 6)))
    sh.col_width(2, 2, min(48, max(22, w_b + 6)))
    sh.col_width(3, 3, 15)
    sh.col_width(4, 4, 17)
    sh.col_width(5, 5, 14)
    return sh


def _matrix_sheet(strings: _SharedStrings, matrix: ComparisonMatrix, threshold: float) -> _Sheet:
    sh = _Sheet(strings)
    names = matrix.names
    sh.put_str(1, 1, "File", "th", height=30.0)
    for j, name in enumerate(names, start=2):
        sh.put_str(j, 1, name, "th", height=30.0)
    sh.freeze(1, 1)

    for i, row_name in enumerate(names):
        r = 2 + i
        sh.put_str(1, r, row_name, "row_head", height=22.0)
        for j in range(len(names)):
            c = 2 + j
            if i == j:
                sh.put_str(c, r, "—", "diag", height=22.0)
            else:
                score = float(matrix.get(i, j))
                sh.put_num(c, r, score, _pct_style(score, threshold), height=22.0)

    first_w = min(46, max(20, max((len(nm) for nm in names), default=14) + 5))
    sh.col_width(1, 1, first_w)
    for j, name in enumerate(names, start=2):
        sh.col_width(j, j, min(26, max(14, len(name) * 0.65 + 6)))
    return sh


def _files_sheet(
    strings: _SharedStrings,
    names: list[str],
    similarity_indices: dict[str, float] | None,
    source_breakdowns: dict[str, list[dict]] | None,
    threshold: float,
    mode: str,
    algorithm: str,
    min_match_words: int,
    scan_uuid: str | None,
    created_at: str | None,
) -> _Sheet:
    sh = _Sheet(strings)
    indices = similarity_indices or {}
    breakdowns = source_breakdowns or {}

    for col, title in enumerate(("File", "Matched", "Closest file", "Closest overlap"), start=1):
        sh.put_str(col, 1, title, "th", height=25.0)
    sh.freeze(0, 1)

    ranked = sorted(names, key=lambda nm: float(indices.get(nm, 0.0)), reverse=True)
    for idx, name in enumerate(ranked, start=2):
        sim = float(indices.get(name, 0.0))
        sources = breakdowns.get(name) or []
        top_src = str(sources[0]["source"]) if sources else "—"
        raw_c = sources[0].get("contribution", sources[0].get("share")) if sources else None

        sh.put_str(1, idx, name, "text")
        sh.put_num(2, idx, sim, _pct_style(sim, threshold))
        sh.put_str(3, idx, top_src, "text" if sources else "muted")
        if raw_c is not None:
            sh.put_num(4, idx, float(raw_c), _pct_style(float(raw_c), threshold))
        else:
            sh.put_str(4, idx, "—", "muted")

    # Compact scan parameters tucked cleanly two rows below the table
    meta_start = len(ranked) + 4
    meta_rows = [
        ("Mode", mode),
        ("Algorithm", algorithm),
        ("Threshold", f"{threshold * 100:.0f}%"),
        ("Min match", f"{min_match_words} words"),
    ]
    if scan_uuid:
        meta_rows.insert(0, ("Scan ID", scan_uuid[:8]))
    if created_at:
        meta_rows.append(("Created", str(created_at)[:19].replace("T", " ")))

    for offset, (k, v) in enumerate(meta_rows):
        r = meta_start + offset
        sh.put_str(1, r, k, "row_head")
        sh.put_str(2, r, v, "muted")

    max_doc = max((len(nm) for nm in names), default=18)
    sh.col_width(1, 1, min(48, max(22, max_doc + 6)))
    sh.col_width(2, 2, 18)
    sh.col_width(3, 3, min(48, max(22, max_doc + 6)))
    sh.col_width(4, 4, 18)
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
    """Serialize a clean 3-sheet `.xlsx` workbook (`Pairs`, `Matrix`, `Files`)."""
    strings = _SharedStrings()
    resolved_pairs = pairs if pairs is not None else matrix.all_pairs()
    algo_label = algorithm or "auto"

    s_pairs = _pairs_sheet(strings, resolved_pairs, threshold)
    s_matrix = _matrix_sheet(strings, matrix, threshold)
    s_files = _files_sheet(
        strings,
        matrix.names,
        similarity_indices,
        source_breakdowns,
        threshold,
        mode,
        algo_label,
        min_match_words,
        scan_uuid,
        created_at,
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
        '<sheet name="Pairs" sheetId="1" r:id="rId1"/>'
        '<sheet name="Matrix" sheetId="2" r:id="rId2"/>'
        '<sheet name="Files" sheetId="3" r:id="rId3"/>'
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
        zf.writestr("xl/worksheets/sheet1.xml", s_pairs.to_xml(active=True))
        zf.writestr("xl/worksheets/sheet2.xml", s_matrix.to_xml())
        zf.writestr("xl/worksheets/sheet3.xml", s_files.to_xml())
        zf.writestr("xl/sharedStrings.xml", strings.to_xml())
    return buf.getvalue()
