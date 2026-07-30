""" engine.py — AlgorithmEngine. """
import itertools

from .matrix import ComparisonMatrix
from .models import ASTModel, CosineModel, JaccardModel, WinnowingModel

#: Fixed weights for the "all" blended algorithm. The three text-based
#: models always contribute; AST only contributes when both files in the
#: pair are Python, so its weight is redistributed proportionally across
#: the remaining models for that pair (see `_compute_all`). This keeps a
#: mixed batch's "all" scores comparable pair-to-pair, unlike a plain
#: average whose denominator silently shrinks when AST is skipped.
_ALL_WEIGHTS = {"cosine": 0.35, "winnowing": 0.35, "jaccard": 0.15, "ast": 0.15}


class AlgorithmEngine:
    """Orchestrates pairwise similarity scans over a batch of files."""

    def __init__(self, algorithm: str = "cosine"):
        """Select which similarity algorithm to run (see VALID_ALGORITHMS)."""
        self.algorithm = algorithm
        self.models = {
            "cosine": CosineModel(),
            "winnowing": WinnowingModel(),
            "jaccard": JaccardModel(),
            "ast": ASTModel(),
        }

    def compute(self, file_data: dict) -> ComparisonMatrix:
        """Score every unique pair in `file_data` and return the matrix."""
        names = list(file_data.keys())
        matrix = ComparisonMatrix(names)

        for name_a, name_b in itertools.combinations(names, 2):
            data_a = file_data[name_a]
            data_b = file_data[name_b]

            score = self._compute_pair(data_a, data_b)

            i = names.index(name_a)
            j = names.index(name_b)
            matrix.set(i, j, score)

        return matrix

    def _compute_pair(self, data_a: dict, data_b: dict) -> float:
        algo = self.algorithm.lower()
        if algo == "all":
            return self._compute_all(data_a, data_b)

        if algo == "ast":
            if data_a["is_python"] and data_b["is_python"]:
                return self.models["ast"].compute([data_a["raw"]], [data_b["raw"]])
            return 0.0

        model = self.models.get(algo, self.models["cosine"])
        return model.compute(data_a["tokens"], data_b["tokens"])

    def _compute_all(self, data_a: dict, data_b: dict) -> float:
        """Weighted blend of every model, renormalized when AST is skipped."""
        both_python = data_a["is_python"] and data_b["is_python"]
        active = dict(_ALL_WEIGHTS) if both_python else {
            name: w for name, w in _ALL_WEIGHTS.items() if name != "ast"
        }
        total_weight = sum(active.values())

        score = 0.0
        for name, weight in active.items():
            model = self.models[name]
            if name == "ast":
                pair_score = model.compute([data_a["raw"]], [data_b["raw"]])
            else:
                pair_score = model.compute(data_a["tokens"], data_b["tokens"])
            score += pair_score * (weight / total_weight)
        return score
