""" test_loader.py — FileLoader validation and ingestion tests. """
import os

import pytest

from src.loader import FileLoader, FileLoadError


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
