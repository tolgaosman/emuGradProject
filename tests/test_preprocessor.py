""" test_preprocessor.py — Preprocessor tokenization, stopwords, exclusions. """
from src.preprocessor import Preprocessor


def test_tc06_lowercasing_and_punctuation_strip():
    """TC-06: text is lowercased and punctuation removed."""
    # Use a path that does not exist so no exclusions are merged.
    pre = Preprocessor(k=2, exclusions_path="__no_such_file__")
    tokens, _ = pre.process("Hello, WORLD!!! Foo-Bar.")
    assert all(t == t.lower() for t in tokens)
    assert not any(any(c in t for c in ",.!-") for t in tokens)


def test_tc07_stopword_removal():
    """TC-07: common English stopwords are removed."""
    pre = Preprocessor(k=2, exclusions_path="__no_such_file__")
    tokens, _ = pre.process("the cat is on the mat and it is happy")
    # Stemmed stopwords like 'the', 'is', 'on', 'and', 'it' should be gone.
    assert "the" not in tokens
    assert "is" not in tokens
    assert "and" not in tokens


def test_tc08_kgram_generation_count():
    """TC-08: number of k-grams equals len(tokens) - k + 1."""
    pre = Preprocessor(k=3, exclusions_path="__no_such_file__")
    tokens, kgrams = pre.process("alpha beta gamma delta epsilon zeta")
    if len(tokens) >= 3:
        assert len(kgrams) == len(tokens) - 3 + 1
    for kg in kgrams:
        assert len(kg.split()) == 3


def test_tc09_exclusion_term_removed(tmp_path):
    """TC-09: a term listed in the exclusions file is filtered out."""
    excl = tmp_path / "exclusions.txt"
    excl.write_text("# comment\nmethodology\nplagiarism\n", encoding="utf-8")

    pre = Preprocessor(k=2, exclusions_path=str(excl))
    stemmer = pre.stemmer

    tokens, _ = pre.process("This methodology describes plagiarism detection clearly")

    assert stemmer.stem("methodology") not in tokens
    assert stemmer.stem("plagiarism") not in tokens
    # A non-excluded content word survives.
    assert stemmer.stem("detection") in tokens


def test_exclusions_absent_file_is_noop():
    """A missing exclusions file does not raise and leaves stopwords intact."""
    pre = Preprocessor(k=2, exclusions_path="definitely_missing_path.txt")
    tokens, _ = pre.process("methodology detection algorithm")
    # Without the exclusion list, 'methodology' stem survives.
    assert pre.stemmer.stem("methodology") in tokens


def test_python_source_tokenized_via_tokenize_module():
    """is_python=True keeps identifiers/keywords intact instead of running
    prose punctuation-stripping over the source."""
    pre = Preprocessor(k=2, exclusions_path="__no_such_file__")
    code = "def add(alpha, beta):\n    return alpha + beta\n"
    tokens, _ = pre.process(code, is_python=True)
    assert pre.stemmer.stem("alpha") in tokens
    assert pre.stemmer.stem("add") in tokens


def test_python_source_falls_back_to_prose_on_syntax_error():
    """Unparseable Python source still yields tokens via the prose fallback,
    instead of raising."""
    pre = Preprocessor(k=2, exclusions_path="__no_such_file__")
    broken = "def broken(:\n    alpha beta\n"
    tokens, _ = pre.process(broken, is_python=True)
    assert isinstance(tokens, list)
    assert pre.stemmer.stem("alpha") in tokens
