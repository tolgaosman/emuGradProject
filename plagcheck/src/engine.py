""" engine.py — ScanEngine: orchestrates the two similarity modes. """
import itertools
from dataclasses import dataclass, field

from . import similarity_index
from .matrix import ComparisonMatrix
from .models import ASTModel, CosineModel, JaccardModel, WinnowingModel

#: Algorithms selectable per similarity mode, in UI display order. "auto" is
#: the default and scores by matched-span coverage (see `compute`); the rest
#: force a single named model, for demoing/reviewing each one individually.
#: AST needs raw Python source (`data["raw"]`, not `data["tokens"]`) and
#: always scores 0.0 on non-Python input — callers should disable that choice
#: for non-Python pairs rather than surface a misleading zero.
ALGORITHMS_BY_MODE: dict[str, list[str]] = {
    "code_similarity": ["auto", "ast", "winnowing", "jaccard"],
    "text_similarity": ["auto", "cosine", "winnowing", "jaccard"],
}


@dataclass
class ScanResult:
    """Unified result of one `ScanEngine.compute()` call."""

    mode: str
    names: list[str]
    algorithm: str = "auto"
    matrix: ComparisonMatrix | None = None
    similarity_indices: dict[str, float] = field(default_factory=dict)
    source_breakdowns: dict[str, list[dict]] = field(default_factory=dict)


class ScanEngine:
    """Orchestrates similarity scans over a batch of files."""

    def __init__(self, mode: str = "text_similarity", algorithm: str = "auto"):
        """Select which mode to run, and optionally force a single algorithm.

        `algorithm="auto"` (default) scores by matched-span coverage, so the
        score is literally the fraction of the document the comparison view
        highlights. Any other value (`ast`, `cosine`, `winnowing`, `jaccard`)
        forces that one model instead, for demoing/reviewing it on its own —
        those raw model scores are *not* coverage and may not line up with
        the highlighting.
        """
        self.mode = mode.lower()
        self.algorithm = algorithm.lower()
        self.models = {
            "cosine": CosineModel(),
            "winnowing": WinnowingModel(),
            "jaccard": JaccardModel(),
            "ast": ASTModel(),
        }

    def compute(
        self,
        file_data: dict,
        preprocessor=None,
        min_match_words: int = similarity_index.DEFAULT_MIN_MATCH_WORDS,
    ) -> ScanResult:
        """Run the scan and return a `ScanResult`.

        With a `preprocessor` (both real callers supply one), matched spans
        are computed once per pair and everything else is derived from them:
        the matrix scores under `algorithm="auto"`, the per-document
        Similarity Index, and the ranked source breakdown. Without one, the
        index/breakdown are skipped and `auto` degrades to winnowing — a
        library/test path, since span matching needs the stemmer and
        stopword set.
        """
        names = list(file_data.keys())
        result = ScanResult(mode=self.mode, names=names, algorithm=self.algorithm)

        pair_spans = None
        if preprocessor is not None:
            pair_spans, indices, breakdowns = similarity_index.compute_all(
                file_data, preprocessor, min_match_words
            )
            result.similarity_indices = indices
            result.source_breakdowns = breakdowns

        matrix = ComparisonMatrix(names)
        for name_a, name_b in itertools.combinations(names, 2):
            data_a, data_b = file_data[name_a], file_data[name_b]
            if self.algorithm == "auto" and pair_spans is not None:
                spans_a, spans_b = pair_spans[(name_a, name_b)]
                score = similarity_index.pair_score(
                    data_a["raw"], data_b["raw"], spans_a, spans_b
                )
            else:
                score = self._compute_pair(data_a, data_b)
            matrix.set(names.index(name_a), names.index(name_b), score)
        result.matrix = matrix

        return result

    def _compute_pair(self, data_a: dict, data_b: dict) -> float:
        if self.algorithm == "ast":
            return self.models["ast"].compute([data_a["raw"]], [data_b["raw"]])
        if self.algorithm in ("cosine", "winnowing", "jaccard"):
            return self.models[self.algorithm].compute(data_a["tokens"], data_b["tokens"])

        # algorithm == "auto" with no preprocessor: `compute()` handles the
        # real coverage path, so reaching here means span matching wasn't
        # possible. Winnowing is the closest standalone stand-in (it is
        # k-gram based like the span matcher), but note it under-reports
        # badly on short inputs — it needs >= k + w - 1 (8) tokens to produce
        # any fingerprint at all.
        return self.models["winnowing"].compute(data_a["tokens"], data_b["tokens"])
