""" engine.py — ScanEngine: orchestrates the four scanning modes. """
import itertools
from dataclasses import dataclass, field

from . import similarity_index
from .matrix import ComparisonMatrix
from .models import ASTModel, CosineModel, JaccardModel, WinnowingModel
from .models.ai_detector import AIAssessment, AIDetector

#: Composition weights per similarity mode. Both modes blend two of the four
#: documented algorithms rather than picking one, mirroring how a real
#: plagiarism check triangulates evidence:
#:  - code_similarity: AST is the only rename-invariant signal, so it
#:    dominates (0.70) whenever both files are Python; winnowing (0.30)
#:    catches copy-paste-with-edits. Non-Python code (Java/C/C++) has no AST
#:    model, so it falls back to winnowing alone.
#:  - text_similarity: TF-IDF cosine (0.50) catches vocabulary-level
#:    similarity, winnowing (0.50) catches contiguous copied passages even
#:    after light paraphrasing — neither alone is sufficient.
_CODE_AST_WEIGHT = 0.70
_CODE_WINNOWING_WEIGHT = 0.30
_TEXT_COSINE_WEIGHT = 0.50
_TEXT_WINNOWING_WEIGHT = 0.50


@dataclass
class ScanResult:
    """Unified result of one `ScanEngine.compute()` call.

    Similarity modes (`code_similarity`, `text_similarity`) populate
    `matrix`, `similarity_indices`, and `source_breakdowns`. AI modes
    (`ai_code`, `ai_text`) populate `ai_assessments`. The unused half stays
    at its default rather than forcing `isinstance` checks at every call
    site — check `is_ai` instead.
    """

    mode: str
    names: list[str]
    matrix: ComparisonMatrix | None = None
    similarity_indices: dict[str, float] = field(default_factory=dict)
    source_breakdowns: dict[str, list[dict]] = field(default_factory=dict)
    ai_assessments: dict[str, AIAssessment] = field(default_factory=dict)

    @property
    def is_ai(self) -> bool:
        """Whether this result came from an ai_code/ai_text scan."""
        return self.mode in ("ai_code", "ai_text")


class ScanEngine:
    """Orchestrates similarity and AI scans over a batch of files."""

    def __init__(self, mode: str = "text_similarity"):
        """Select which mode to run (code_similarity, text_similarity, ai_code, ai_text)."""
        self.mode = mode.lower()
        self.models = {
            "cosine": CosineModel(),
            "winnowing": WinnowingModel(),
            "jaccard": JaccardModel(),
            "ast": ASTModel(),
            "ai": AIDetector(),
        }

    def compute(
        self,
        file_data: dict,
        preprocessor=None,
        min_match_words: int = similarity_index.DEFAULT_MIN_MATCH_WORDS,
    ) -> ScanResult:
        """Run the scan and return a `ScanResult`.

        `preprocessor` is optional for similarity modes; when supplied, the
        per-document Similarity Index and ranked source breakdown are also
        computed (they need the stemmer/stopword set to find matched spans).
        """
        names = list(file_data.keys())
        result = ScanResult(mode=self.mode, names=names)

        if self.mode in ("ai_code", "ai_text"):
            detector = self.models["ai"]
            for name in names:
                data = file_data[name]
                if self.mode == "ai_code":
                    result.ai_assessments[name] = detector.assess_code(
                        data["raw"], data.get("language", "python")
                    )
                else:
                    result.ai_assessments[name] = detector.assess_text(data["raw"])
            return result

        matrix = ComparisonMatrix(names)
        for name_a, name_b in itertools.combinations(names, 2):
            data_a, data_b = file_data[name_a], file_data[name_b]
            score = self._compute_pair(data_a, data_b)
            matrix.set(names.index(name_a), names.index(name_b), score)
        result.matrix = matrix

        if preprocessor is not None:
            for name in names:
                result.similarity_indices[name] = similarity_index.similarity_index(
                    name, file_data, preprocessor, min_match_words
                )
                result.source_breakdowns[name] = similarity_index.source_breakdown(
                    name, file_data, preprocessor, min_match_words
                )

        return result

    def _compute_pair(self, data_a: dict, data_b: dict) -> float:
        if self.mode == "code_similarity":
            if data_a.get("language") == "python" and data_b.get("language") == "python":
                ast_score = self.models["ast"].compute([data_a["raw"]], [data_b["raw"]])
                win_score = self.models["winnowing"].compute(data_a["tokens"], data_b["tokens"])
                return (ast_score * _CODE_AST_WEIGHT) + (win_score * _CODE_WINNOWING_WEIGHT)
            # Non-Python code (Java/C/C++): no AST model, winnowing alone.
            return self.models["winnowing"].compute(data_a["tokens"], data_b["tokens"])

        if self.mode == "text_similarity":
            cos_score = self.models["cosine"].compute(data_a["tokens"], data_b["tokens"])
            win_score = self.models["winnowing"].compute(data_a["tokens"], data_b["tokens"])
            return (cos_score * _TEXT_COSINE_WEIGHT) + (win_score * _TEXT_WINNOWING_WEIGHT)

        # Fallback for an unrecognized mode.
        return self.models["jaccard"].compute(data_a["tokens"], data_b["tokens"])
