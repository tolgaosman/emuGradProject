""" engine.py — AlgorithmEngine. """
import itertools
from .matrix import ComparisonMatrix
from .models import CosineModel, WinnowingModel, JaccardModel, ASTModel

class AlgorithmEngine:
    def __init__(self, algorithm: str = "cosine"):
        self.algorithm = algorithm
        self.models = {
            "cosine": CosineModel(),
            "winnowing": WinnowingModel(),
            "jaccard": JaccardModel(),
            "ast": ASTModel()
        }

    def compute(self, file_data: dict) -> ComparisonMatrix:
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
            scores = []
            for name, model in self.models.items():
                if name == "ast":
                    if data_a["is_python"] and data_b["is_python"]:
                        scores.append(model.compute([data_a["raw"]], [data_b["raw"]]))
                else:
                    scores.append(model.compute(data_a["tokens"], data_b["tokens"]))
            return sum(scores) / len(scores) if scores else 0.0
            
        if algo == "ast":
            if data_a["is_python"] and data_b["is_python"]:
                return self.models["ast"].compute([data_a["raw"]], [data_b["raw"]])
            return 0.0
            
        model = self.models.get(algo, self.models["cosine"])
        return model.compute(data_a["tokens"], data_b["tokens"])
