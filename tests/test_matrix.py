""" test_matrix.py — ComparisonMatrix storage, symmetry, flagging, CSV. """
import pytest
from src.matrix import ComparisonMatrix


def test_diagonal_is_one():
    m = ComparisonMatrix(["a", "b", "c"])
    for i in range(3):
        assert m.get(i, i) == pytest.approx(1.0)


def test_set_is_symmetric():
    m = ComparisonMatrix(["a", "b"])
    m.set(0, 1, 0.42)
    assert m.get(0, 1) == pytest.approx(0.42)
    assert m.get(1, 0) == pytest.approx(0.42)


def test_get_flagged_threshold():
    m = ComparisonMatrix(["a", "b", "c"])
    m.set(0, 1, 0.80)
    m.set(0, 2, 0.50)
    flagged = m.get_flagged(0.70)
    pairs = {(f["file_a"], f["file_b"]) for f in flagged}
    assert ("a", "b") in pairs
    assert ("a", "c") not in pairs


def test_to_csv_shape():
    m = ComparisonMatrix(["a", "b"])
    m.set(0, 1, 0.5)
    csv = m.to_csv()
    lines = csv.splitlines()
    # header + one row per file
    assert len(lines) == 3
    assert lines[0] == ",a,b"


def test_to_csv_quotes_names_containing_commas():
    """Display names are original upload filenames now, so one containing a
    comma would shift every column in its row if joined naively."""
    import csv as csv_module
    import io

    m = ComparisonMatrix(["rapor, kopya.txt", "b.txt"])
    m.set(0, 1, 0.5)
    rows = list(csv_module.reader(io.StringIO(m.to_csv())))
    assert rows[0] == ["", "rapor, kopya.txt", "b.txt"]
    assert rows[1][0] == "rapor, kopya.txt"
    assert len(rows[1]) == 3
