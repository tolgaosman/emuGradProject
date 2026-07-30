""" ai_detector.py — AI-generation detection.

A fully offline heuristic estimator, not a trained classifier. It is
materially less accurate than a service like Turnitin's own AI detector and
**will produce false positives** — every score is an indicative signal for a
human reviewer, never evidence of misconduct on its own. Callers must surface
that caveat alongside every result; see `AIAssessment.band`.
"""
import math
import re
from dataclasses import dataclass

from ..language import CODE_LANGUAGES, line_comment_prefix, strip_comments_and_strings

# Banding thresholds. Deliberately coarse (three bands, not a raw percentage
# presented as fact) so the UI can't imply more precision than a heuristic
# actually has.
_BAND_LOW_MAX = 0.35
_BAND_POSSIBLE_MAX = 0.65

_HEDGE_PHRASES = (
    "furthermore", "moreover", "additionally", "consequently", "therefore",
    "however", "nevertheless", "nonetheless", "overall", "ultimately",
    "in conclusion", "it is important to note", "it is worth noting",
    "in summary", "as a result", "on the other hand", "in other words",
)
_GENERIC_IDENTIFIERS = {
    "data", "result", "temp", "tmp", "value", "val", "item", "output",
    "input", "arr", "array", "num", "res", "obj", "list", "str", "count",
    "flag", "index", "idx",
}
_SENTENCE_RE = re.compile(r"[^.!?]*[.!?]+|\S[^.!?]*$")


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _band(probability: float) -> str:
    if probability < _BAND_LOW_MAX:
        return "low"
    if probability < _BAND_POSSIBLE_MAX:
        return "possible"
    return "likely"


@dataclass
class Signal:
    """One scored heuristic and its weight in the overall blend.

    `score` is 0.0-1.0, higher meaning more AI-like.
    """

    name: str
    score: float
    weight: float

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation of this signal."""
        return {"name": self.name, "score": round(self.score, 4), "weight": self.weight}


@dataclass
class Segment:
    """A scored character span (sentence or code block) for highlighting."""

    start: int
    end: int
    probability: float

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation of this segment."""
        return {"start": self.start, "end": self.end, "probability": round(self.probability, 4)}


@dataclass
class AIAssessment:
    """The full result of one AI-detection pass over a single document."""

    overall_probability: float
    band: str
    signals: list[Signal]
    segments: list[Segment]

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation of this assessment."""
        return {
            "overall_probability": round(self.overall_probability, 4),
            "band": self.band,
            "signals": [s.to_dict() for s in self.signals],
            "segments": [s.to_dict() for s in self.segments],
        }


class AIDetector:
    """Heuristic AI-generation probability estimator for text and code."""

    def assess_text(self, text: str) -> AIAssessment:
        """Score prose across lexical/structural signals, with per-sentence segments."""
        sentences = self._split_sentences(text)
        if not sentences:
            return AIAssessment(0.0, "low", [], [])

        signals = [
            self._sig_burstiness(sentences),
            self._sig_lexical_diversity(text),
            self._sig_repetition(text),
            self._sig_punctuation_diversity(text),
            self._sig_hedge_density(text),
            self._sig_contraction_rate(text),
        ]
        overall = self._combine(signals)
        segments = [
            Segment(start, end, self._sentence_probability(sentence, overall))
            for sentence, start, end in sentences
        ]
        return AIAssessment(overall, _band(overall), signals, segments)

    def assess_code(self, text: str, language: str = "python") -> AIAssessment:
        """Score source code across structural signals, with per-block segments."""
        if not text.strip():
            return AIAssessment(0.0, "low", [], [])

        signals = [
            self._sig_comment_ratio(text, language),
            self._sig_generic_identifiers(text),
            self._sig_line_length_uniformity(text, language),
            self._sig_blank_line_rhythm(text),
            self._sig_indentation_regularity(text),
        ]
        overall = self._combine(signals)
        segments = self._code_segments(text, overall)
        return AIAssessment(overall, _band(overall), signals, segments)

    # -- back-compat single-float convenience wrappers ----------------------

    def compute_text_probability(self, text: str) -> float:
        """Return just the overall AI probability for prose text."""
        return self.assess_text(text).overall_probability

    def compute_code_probability(self, text: str, language: str = "python") -> float:
        """Return just the overall AI probability for source code."""
        return self.assess_code(text, language).overall_probability

    # -- combining ------------------------------------------------------

    def _combine(self, signals: list[Signal]) -> float:
        total_weight = sum(s.weight for s in signals) or 1.0
        raw = sum(s.score * s.weight for s in signals) / total_weight
        # Never claim certainty either way — this is a heuristic, not a verdict.
        return _clamp(raw, 0.05, 0.95)

    # -- text signals --------------------------------------------------

    def _split_sentences(self, text: str) -> list[tuple[str, int, int]]:
        out = []
        for m in _SENTENCE_RE.finditer(text):
            sentence = m.group()
            if sentence.strip():
                out.append((sentence, m.start(), m.end()))
        return out

    def _sig_burstiness(self, sentences: list[tuple[str, int, int]]) -> Signal:
        """Human prose mixes short/long sentences ("burstiness").

        AI text tends toward more uniform sentence lengths.
        """
        lengths = [len(sentence.split()) for sentence, _, _ in sentences]
        if len(lengths) < 2:
            return Signal("burstiness", 0.5, 1.2)
        mean = sum(lengths) / len(lengths)
        stdev = math.sqrt(sum((n - mean) ** 2 for n in lengths) / len(lengths))
        cv = stdev / mean if mean else 0.0
        return Signal("burstiness", _clamp(1.0 - (cv / 0.6)), 1.5)

    def _sig_lexical_diversity(self, text: str) -> Signal:
        """Longer AI passages often settle into a narrower vocabulary."""
        words = re.findall(r"[a-zA-Z']+", text.lower())
        if len(words) < 10:
            return Signal("lexical_diversity", 0.5, 1.0)
        ttr = len(set(words)) / len(words)
        return Signal("lexical_diversity", _clamp(1.0 - (ttr / 0.55)), 1.2)

    def _sig_repetition(self, text: str) -> Signal:
        """AI text repeats phrasing (trigrams) more than typical human prose."""
        words = re.findall(r"[a-zA-Z']+", text.lower())
        if len(words) < 6:
            return Signal("repetition", 0.0, 1.0)
        trigrams = [tuple(words[i : i + 3]) for i in range(len(words) - 2)]
        if not trigrams:
            return Signal("repetition", 0.0, 1.0)
        repeated = len(trigrams) - len(set(trigrams))
        return Signal("repetition", _clamp((repeated / len(trigrams)) / 0.15), 1.3)

    def _sig_punctuation_diversity(self, text: str) -> Signal:
        """Human writing tends to use a wider range of punctuation marks."""
        marks = re.findall(r"[,;:\-—()\"'!?]", text)
        if len(marks) < 5:
            return Signal("punctuation_diversity", 0.4, 0.8)
        diversity = len(set(marks)) / min(len(marks), 8)
        return Signal("punctuation_diversity", _clamp(1.0 - diversity), 0.8)

    def _sig_hedge_density(self, text: str) -> Signal:
        """AI writing over-uses formal transition/hedge phrases."""
        lowered = text.lower()
        hits = sum(lowered.count(phrase) for phrase in _HEDGE_PHRASES)
        words = max(1, len(re.findall(r"\w+", text)))
        density_per_100_words = hits / words * 100
        return Signal("hedge_density", _clamp(density_per_100_words / 3.0), 1.4)

    def _sig_contraction_rate(self, text: str) -> Signal:
        """Formal, contraction-free prose reads as more AI-like."""
        words = re.findall(r"\w+", text)
        if len(words) < 20:
            return Signal("contraction_rate", 0.5, 0.6)
        contractions = len(re.findall(r"\b\w+'(?:t|re|ve|ll|d|s|m)\b", text, re.I))
        rate_per_100_words = contractions / len(words) * 100
        return Signal("contraction_rate", _clamp(1.0 - (rate_per_100_words / 1.5)), 0.7)

    def _sentence_probability(self, sentence: str, overall: float) -> float:
        """Blend the document's overall score with a light per-sentence cue.

        Very average-length sentences read as more uniform/AI-like.
        """
        length = len(sentence.split())
        local = 0.65 if 12 <= length <= 28 else (0.3 if length < 5 else 0.5)
        return _clamp(0.6 * overall + 0.4 * local, 0.05, 0.95)

    # -- code signals -----------------------------------------------------

    def _sig_comment_ratio(self, text: str, language: str) -> Signal:
        """AI-generated code is often over-commented vs. a human baseline.

        Compared against a typical human baseline of ~15% of lines.
        """
        code_lines = [line for line in text.splitlines() if line.strip()]
        if not code_lines:
            return Signal("comment_ratio", 0.0, 1.0)

        prefix = line_comment_prefix(language) if language in CODE_LANGUAGES else "#"
        comment_lines = [
            line for line in code_lines if prefix and line.strip().startswith(prefix)
        ]
        ratio = len(comment_lines) / len(code_lines)
        baseline = 0.15
        score = 0.15 if ratio <= baseline else 0.15 + (ratio - baseline) / 0.35 * 0.85
        return Signal("comment_ratio", _clamp(score), 1.0)

    def _sig_generic_identifiers(self, text: str) -> Signal:
        """AI code disproportionately reaches for generic names like `data`/`result`."""
        idents = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{1,}\b", text)
        if len(idents) < 5:
            return Signal("generic_identifiers", 0.3, 0.8)
        generic = sum(1 for ident in idents if ident.lower() in _GENERIC_IDENTIFIERS)
        return Signal("generic_identifiers", _clamp((generic / len(idents)) / 0.25), 1.0)

    def _sig_line_length_uniformity(self, text: str, language: str) -> Signal:
        """AI code tends toward more uniform line lengths than hand-written code."""
        source = strip_comments_and_strings(text, language) if language in CODE_LANGUAGES else text
        lines = [line for line in source.splitlines() if line.strip()]
        if len(lines) < 4:
            return Signal("line_length_uniformity", 0.4, 0.8)
        lengths = [len(line) for line in lines]
        mean = sum(lengths) / len(lengths)
        stdev = math.sqrt(sum((n - mean) ** 2 for n in lengths) / len(lengths))
        cv = stdev / mean if mean else 0.0
        return Signal("line_length_uniformity", _clamp(1.0 - (cv / 0.7)), 1.1)

    def _sig_blank_line_rhythm(self, text: str) -> Signal:
        """Very regular spacing between blank-line-separated blocks reads as AI-like."""
        lines = text.splitlines()
        if len(lines) < 6:
            return Signal("blank_line_rhythm", 0.3, 0.6)
        gaps: list[int] = []
        since_blank = 0
        for line in lines:
            if not line.strip():
                gaps.append(since_blank)
                since_blank = 0
            else:
                since_blank += 1
        if len(gaps) < 2:
            return Signal("blank_line_rhythm", 0.3, 0.6)
        mean = sum(gaps) / len(gaps)
        stdev = math.sqrt(sum((g - mean) ** 2 for g in gaps) / len(gaps))
        cv = stdev / mean if mean else 0.0
        return Signal("blank_line_rhythm", _clamp(1.0 - (cv / 0.8)), 0.7)

    def _sig_indentation_regularity(self, text: str) -> Signal:
        """Score extremely uniform indentation depth.

        Weighted low since well-formatted human code is regular too.
        """
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) < 4:
            return Signal("indentation_regularity", 0.4, 0.7)
        depths = [len(line) - len(line.lstrip(" \t")) for line in lines]
        mean = sum(depths) / len(depths)
        stdev = math.sqrt(sum((d - mean) ** 2 for d in depths) / len(depths))
        return Signal("indentation_regularity", _clamp(1.0 - (stdev / 4.0)), 0.6)

    def _code_segments(self, text: str, overall: float) -> list[Segment]:
        """Score each blank-line-separated block, blended with the overall score."""
        segments = []
        pos = 0
        for block in re.split(r"(\n\s*\n)", text):
            start = pos
            pos += len(block)
            if not block.strip():
                continue
            block_lines = len([line for line in block.splitlines() if line.strip()])
            local = 0.6 if block_lines >= 3 else 0.4
            probability = _clamp(0.6 * overall + 0.4 * local, 0.05, 0.95)
            segments.append(Segment(start, pos, probability))
        return segments
