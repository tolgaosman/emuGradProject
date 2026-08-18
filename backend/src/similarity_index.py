""" similarity_index.py — Matched-span coverage metrics.

Everything the scan reports about *how much* two documents share is derived
here from one source of truth: the character ranges `reporter.matched_spans`
highlights. The pairwise matrix score, Turnitin's asymmetric per-document
Similarity Index ("what percentage of THIS document matched something
else"), and the ranked per-source breakdown are three views of that same
computation, so a score can never disagree with what the comparison view
shows.
"""
import itertools
import re

from .reporter import _merge_spans, matched_spans

#: Turnitin's default "exclude matches smaller than N words" setting.
DEFAULT_MIN_MATCH_WORDS = 8

#: Word-like units for the minimum-match-length filter. Deliberately not
#: `str.split()`: whitespace splitting counts `def add(a,b):` as one "word",
#: which made the default of 8 discard essentially every code match and left
#: every code scan reporting a 0.0 Similarity Index.
_WORD_RE = re.compile(r"\w+")

Span = tuple[int, int]
#: `{(name_a, name_b): (spans_in_a, spans_in_b)}`, keyed by the
#: `itertools.combinations` ordering of the batch's file names.
PairSpans = dict[tuple[str, str], tuple[list[Span], list[Span]]]


def _filter_by_word_count(text: str, spans: list[Span], min_words: int) -> list[Span]:
    """Drop spans covering fewer than `min_words` word-like units."""
    if min_words <= 0:
        return spans
    return [
        (start, end)
        for start, end in spans
        if len(_WORD_RE.findall(text[start:end])) >= min_words
    ]


def _coverage_ratio(text: str, spans: list[Span]) -> float:
    if not text.strip():
        return 0.0
    covered = sum(end - start for start, end in spans)
    return min(1.0, covered / len(text))


def pair_score(text_a: str, text_b: str, spans_a: list[Span], spans_b: list[Span]) -> float:
    """Symmetric similarity for one pair: the larger of the two coverages.

    Coverage is inherently asymmetric — a short document copied wholesale
    into a long one is 100% covered while the long one is barely touched.
    Taking the max keeps that containment visible (the same call Turnitin
    makes), and gives `ComparisonMatrix` the single symmetric value it
    stores per pair.
    """
    return max(_coverage_ratio(text_a, spans_a), _coverage_ratio(text_b, spans_b))


def compute_all(
    file_data: dict,
    preprocessor,
    min_match_words: int = DEFAULT_MIN_MATCH_WORDS,
) -> tuple[PairSpans, dict[str, float], dict[str, list[dict]]]:
    """Compute matched spans once per pair, then derive every coverage metric.

    Returns `(pair_spans, indices, breakdowns)` where `pair_spans` is keyed
    by the `itertools.combinations` ordering of `file_data`'s keys and holds
    the `min_match_words`-filtered spans for each side.

    Span matching is by far the most expensive step in a scan, so it runs
    exactly once per unordered pair here — `N(N-1)/2` calls. Computing the
    matrix, the indices and the breakdowns separately would repeat it.
    """
    names = list(file_data)
    pair_spans: PairSpans = {}

    for name_a, name_b in itertools.combinations(names, 2):
        data_a, data_b = file_data[name_a], file_data[name_b]
        spans_a, spans_b = matched_spans(
            data_a["raw"], data_b["raw"], data_a["language"], data_b["language"], preprocessor
        )
        pair_spans[(name_a, name_b)] = (
            _filter_by_word_count(data_a["raw"], spans_a, min_match_words),
            _filter_by_word_count(data_b["raw"], spans_b, min_match_words),
        )

    indices: dict[str, float] = {}
    breakdowns: dict[str, list[dict]] = {}

    for name in names:
        text = file_data[name]["raw"]
        per_source: dict[str, list[Span]] = {}
        for other in names:
            if other == name:
                continue
            if (name, other) in pair_spans:
                spans = pair_spans[(name, other)][0]
            else:
                spans = pair_spans[(other, name)][1]
            if spans:
                per_source[other] = spans

        all_spans = [span for spans in per_source.values() for span in spans]
        indices[name] = _coverage_ratio(text, _merge_spans(all_spans))
        breakdowns[name] = sorted(
            (
                {
                    "source": other,
                    "contribution": _coverage_ratio(text, spans),
                    "spans": [[start, end] for start, end in spans],
                }
                for other, spans in per_source.items()
            ),
            key=lambda item: item["contribution"],
            reverse=True,
        )

    return pair_spans, indices, breakdowns


def pairwise_matches(
    name: str,
    file_data: dict,
    preprocessor,
    min_match_words: int = DEFAULT_MIN_MATCH_WORDS,
) -> dict[str, list[Span]]:
    """Return `{other_name: spans_in_name's_text}` for every overlapping file.

    Filtered by `min_match_words`. Prefer `compute_all()` when you need this
    for more than one file — it shares the span matching across the batch
    instead of redoing it per call.
    """
    target = file_data[name]
    matches: dict[str, list[Span]] = {}
    for other_name, other in file_data.items():
        if other_name == name:
            continue
        spans_in_target, _ = matched_spans(
            target["raw"], other["raw"], target["language"], other["language"], preprocessor
        )
        spans = _filter_by_word_count(target["raw"], spans_in_target, min_match_words)
        if spans:
            matches[other_name] = spans
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
