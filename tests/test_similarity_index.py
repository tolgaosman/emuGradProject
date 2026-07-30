""" test_similarity_index.py — Turnitin-style per-document Similarity Index. """
import pytest
from src.preprocessor import Preprocessor
from src.similarity_index import pairwise_matches, similarity_index, source_breakdown


@pytest.fixture
def pre():
    return Preprocessor(exclusions_path="__no_such_file__")


def _file_data():
    shared = (
        "the quick brown fox jumps over the lazy dog near the riverbank "
        "on a cold autumn morning while the wind blew softly through the trees"
    )
    tail_a = " Unique tail content for file a that matches nothing else."
    tail_b = " Different unique tail content for file b entirely unrelated."
    unrelated = "Nothing in this file relates to the others whatsoever, completely distinct."
    return {
        "a.txt": {"raw": shared + tail_a, "language": "text"},
        "b.txt": {"raw": shared + tail_b, "language": "text"},
        "c.txt": {"raw": unrelated, "language": "text"},
    }


def test_similarity_index_asymmetric_and_bounded(pre):
    file_data = _file_data()
    idx_a = similarity_index("a.txt", file_data, pre)
    idx_b = similarity_index("b.txt", file_data, pre)
    idx_c = similarity_index("c.txt", file_data, pre)

    assert 0.0 <= idx_a <= 1.0
    assert 0.0 <= idx_b <= 1.0
    assert idx_a > 0.0
    assert idx_b > 0.0
    assert idx_c == 0.0  # nothing in c.txt overlaps the other two


def test_source_breakdown_ranked_and_shaped(pre):
    file_data = _file_data()
    breakdown = source_breakdown("a.txt", file_data, pre)
    assert len(breakdown) == 1
    entry = breakdown[0]
    assert entry["source"] == "b.txt"
    assert 0.0 <= entry["contribution"] <= 1.0
    assert entry["spans"]
    # Sorted descending by contribution (trivially true with one entry, but
    # asserts the contract for callers with more sources).
    contributions = [e["contribution"] for e in breakdown]
    assert contributions == sorted(contributions, reverse=True)


def test_pairwise_matches_excludes_self(pre):
    file_data = _file_data()
    matches = pairwise_matches("a.txt", file_data, pre)
    assert "a.txt" not in matches


def test_min_match_words_filters_short_matches(pre):
    file_data = _file_data()
    # A very high min_match_words should filter out all matches, dropping
    # the index to 0 even though shorter overlaps exist.
    idx_strict = similarity_index("a.txt", file_data, pre, min_match_words=1000)
    assert idx_strict == 0.0

    idx_lenient = similarity_index("a.txt", file_data, pre, min_match_words=1)
    assert idx_lenient > 0.0


def test_similarity_index_no_overlap_is_zero(pre):
    x_raw = "Completely distinct statement about astronomy and stars."
    y_raw = "An entirely separate discussion of cooking recipes."
    file_data = {
        "x.txt": {"raw": x_raw, "language": "text"},
        "y.txt": {"raw": y_raw, "language": "text"},
    }
    assert similarity_index("x.txt", file_data, pre) == 0.0
    assert source_breakdown("x.txt", file_data, pre) == []


def test_similarity_index_empty_text_is_zero(pre):
    file_data = {
        "empty.txt": {"raw": "   ", "language": "text"},
        "other.txt": {"raw": "Some real content here for comparison purposes.", "language": "text"},
    }
    assert similarity_index("empty.txt", file_data, pre) == 0.0
