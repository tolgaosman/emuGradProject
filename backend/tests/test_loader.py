""" test_loader.py — FileLoader validation and ingestion tests. """
import os

import pytest
from src.loader import MAX_FILES, FileLoader, FileLoadError

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES_DIR = os.path.join(REPO_ROOT, "samples")


@pytest.fixture
def loader():
    return FileLoader()


def test_tc01_unsafe_filename_rejected(loader, tmp_path):
    """TC-01: filenames with unsafe characters are rejected."""
    bad = tmp_path / "bad name!.txt"
    bad.write_text("data", encoding="utf-8")
    with pytest.raises(FileLoadError):
        loader.load(str(bad))


def test_tc02_path_traversal_rejected(loader):
    """TC-02: paths containing '..' are rejected."""
    with pytest.raises(FileLoadError):
        loader.load("../secret.txt")


def test_tc03_unsupported_extension_rejected(loader, tmp_path):
    """TC-03: unsupported file extensions are rejected."""
    f = tmp_path / "data.exe"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(FileLoadError):
        loader.load(str(f))


def test_tc04_valid_txt_loads(loader, tmp_path):
    """TC-04: a valid .txt file is loaded and its content returned."""
    f = tmp_path / "doc.txt"
    f.write_text("the quick brown fox jumps over the lazy dog", encoding="utf-8")
    text = loader.load(str(f))
    assert "quick brown fox" in text


def test_tc05_oversize_file_rejected(loader, tmp_path, monkeypatch):
    """TC-05: files larger than MAX_BYTES are rejected."""
    f = tmp_path / "big.txt"
    f.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(os.path, "getsize", lambda _p: 20 * 1024 * 1024)
    with pytest.raises(FileLoadError):
        loader.load(str(f))


def test_python_file_loads(loader, tmp_path):
    """A valid .py file loads as text."""
    f = tmp_path / "script.py"
    f.write_text("x = 1\nprint(x)\n", encoding="utf-8")
    text = loader.load(str(f))
    assert "print(x)" in text


def test_empty_file_rejected(loader, tmp_path):
    """An empty file is rejected before any content parsing is attempted."""
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    with pytest.raises(FileLoadError):
        loader.load(str(f))


def test_missing_file_raises_file_load_error(loader, tmp_path):
    """A nonexistent path raises FileLoadError, not a raw OSError."""
    missing = tmp_path / "does_not_exist.txt"
    with pytest.raises(FileLoadError):
        loader.load(str(missing))


def test_symlink_rejected(loader, tmp_path):
    """Symlinked files are rejected regardless of what they point to."""
    target = tmp_path / "real.txt"
    target.write_text("hello world", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation requires elevated privileges on this platform")
    with pytest.raises(FileLoadError):
        loader.load(str(link))


def test_low_confidence_encoding_rejected(loader, tmp_path):
    """Bytes that don't decode confidently as text are rejected."""
    f = tmp_path / "binary.txt"
    f.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(FileLoadError):
        loader.load(str(f))


def test_load_batch_enforces_max_files(loader, tmp_path):
    """A batch larger than MAX_FILES is rejected before touching disk."""
    paths = [str(tmp_path / f"f{i}.txt") for i in range(MAX_FILES + 1)]
    with pytest.raises(FileLoadError):
        loader.load_batch(paths)


def test_load_batch_returns_name_to_text_mapping(loader, tmp_path):
    """load_batch() maps each basename to its extracted text."""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("alpha", encoding="utf-8")
    b.write_text("beta", encoding="utf-8")

    result = loader.load_batch([str(a), str(b)])
    assert result == {"a.txt": "alpha", "b.txt": "beta"}


def test_pdf_loads_via_pdfplumber_or_pymupdf(loader):
    """A real sample PDF extracts non-empty text through the two-stage loader."""
    path = os.path.join(SAMPLES_DIR, "sample_d.pdf")
    if not os.path.isfile(path):
        pytest.skip("sample_d.pdf not present in samples/")
    text = loader.load(path)
    assert text.strip()


def test_docx_loads_paragraph_text(loader):
    """A real sample .docx extracts its paragraph text."""
    path = os.path.join(SAMPLES_DIR, "sample_c.docx")
    if not os.path.isfile(path):
        pytest.skip("sample_c.docx not present in samples/")
    text = loader.load(path)
    assert text.strip()
