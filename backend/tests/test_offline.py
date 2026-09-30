""" test_offline.py — the NLP pipeline never reaches the network. """
import nltk
import pytest

from src import preprocessor as preprocessor_module
from src.preprocessor import Preprocessor


@pytest.fixture
def no_downloads(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("nltk.download must never be called")

    monkeypatch.setattr(nltk, "download", fail)


def test_vendored_nltk_data_is_on_the_search_path():
    assert nltk.data.path[0] == preprocessor_module.NLTK_DATA_DIR
    assert nltk.data.find("corpora/stopwords")
    assert nltk.data.find("tokenizers/punkt_tab/english")


def test_missing_stopwords_degrade_without_downloading(monkeypatch, no_downloads):
    def missing(_language):
        raise LookupError("stopwords")

    monkeypatch.setattr(preprocessor_module.stopwords, "words", missing)
    pre = Preprocessor(k=2, exclusions_path="__no_such_file__")
    assert pre.stop_words == set()
    tokens, _ = pre.process("the fox")
    assert "the" in tokens


def test_missing_punkt_falls_back_to_whitespace_split(monkeypatch, no_downloads):
    def missing(_text):
        raise LookupError("punkt_tab")

    monkeypatch.setattr(preprocessor_module, "word_tokenize", missing)
    pre = Preprocessor(k=2, exclusions_path="__no_such_file__")
    tokens, _ = pre.process("Detection, of copied: paragraphs!")
    assert tokens == [pre.stemmer.stem(w) for w in ("detection", "copied", "paragraphs")]


def test_default_exclusion_list_is_loaded(monkeypatch):
    """FR-15: config/exclusions.txt applies without any flag or env var."""
    monkeypatch.delenv("EXCLUSIONS_PATH", raising=False)
    monkeypatch.delenv("EXCLUSION_LIST_PATH", raising=False)
    pre = Preprocessor(k=2)
    assert pre.stemmer.stem("methodology") in pre.exclusions


def test_report_env_name_for_exclusions_is_honoured(monkeypatch, tmp_path):
    excl = tmp_path / "custom.txt"
    excl.write_text("zebra\n", encoding="utf-8")
    monkeypatch.delenv("EXCLUSIONS_PATH", raising=False)
    monkeypatch.setenv("EXCLUSION_LIST_PATH", str(excl))
    assert Preprocessor(k=2).exclusions == {"zebra"}


def test_exclusions_apply_to_prose_but_not_code(tmp_path):
    excl = tmp_path / "exclusions.txt"
    excl.write_text("result\n", encoding="utf-8")
    pre = Preprocessor(k=2, exclusions_path=str(excl))
    stem = pre.stemmer.stem("result")

    prose, _ = pre.process("the final result was clear", language="text")
    code, _ = pre.process("result = compute(value)\n", language="python")
    assert stem not in prose
    assert stem in code
