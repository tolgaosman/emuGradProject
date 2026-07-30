""" similarity_index.py — Turnitin-style per-document Similarity Index.

Turnitin's headline metric is asymmetric: "what percentage of THIS document
matched something else", ranked by source. The engine's `ComparisonMatrix` is
symmetric pairwise scores instead, which is a different (and for the
heatmap, more useful) view — this module adds the per-document metric on
top, reusing `reporter.matched_spans()` for the actual span matching rather
than re-implementing it.
"""
from .reporter import _merge_spans, matched_spans

#: Turnitin's default "exclude matches smaller than N words" setting.
DEFAULT_MIN_MATCH_WORDS = 8


def _filter_by_word_count(
    text: str, spans: list[tuple[int, int]], min_words: int
) -> list[tuple[int, int]]:
    """Drop spans covering fewer than `min_words` words."""
    if min_words <= 0:
        return spans
    return [(start, end) for start, end in spans if len(text[start:end].split()) >= min_words]


def _coverage_ratio(text: str, spans: list[tuple[int, int]]) -> float:
    if not text.strip():
        return 0.0
    covered = sum(end - start for start, end in spans)
    return min(1.0, covered / len(text))


def pairwise_matches(
    name: str,
    file_data: dict,
    preprocessor,
    min_match_words: int = DEFAULT_MIN_MATCH_WORDS,
) -> dict[str, list[tuple[int, int]]]:
    """Return `{other_name: spans_in_name's_text}` for every overlapping file.

    Filtered by `min_match_words`.
    """
    target = file_data[name]
    matches: dict[str, list[tuple[int, int]]] = {}
    for other_name, other in file_data.items():
        if other_name == name:
            continue
        spans_in_target, _ = matched_spans(
            target["raw"], other["raw"], target["language"], other["language"], preprocessor
        )
        spans_in_target = _filter_by_word_count(target["raw"], spans_in_target, min_match_words)
        if spans_in_target:
            matches[other_name] = spans_in_target
    return matches


def similarity_index(
    name: str,
    file_data: dict,
    preprocessor,
    min_match_words: int = DEFAULT_MIN_MATCH_WORDS,
) -> float:
    """Return the fraction (0.0-1.0) of `name`'s text covered by matches.

    Coverage is computed against any other file in the batch.
    """
    matches = pairwise_matches(name, file_data, preprocessor, min_match_words)
    all_spans = [span for spans in matches.values() for span in spans]
    merged = _merge_spans(all_spans)
    return _coverage_ratio(file_data[name]["raw"], merged)


def source_breakdown(
    name: str,
    file_data: dict,
    preprocessor,
    min_match_words: int = DEFAULT_MIN_MATCH_WORDS,
) -> list[dict]:
    """Return a ranked list of `{source, contribution, spans}`.

    One entry per other file that overlaps `name`, highest contribution
    first — Turnitin's per-source breakdown under the headline Similarity
    Index.
    """
    matches = pairwise_matches(name, file_data, preprocessor, min_match_words)
    text = file_data[name]["raw"]
    breakdown = [
        {
            "source": other_name,
            "contribution": _coverage_ratio(text, spans),
            "spans": [[start, end] for start, end in spans],
        }
        for other_name, spans in matches.items()
    ]
    breakdown.sort(key=lambda item: item["contribution"], reverse=True)
    return breakdown
