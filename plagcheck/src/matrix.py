""" matrix.py — ComparisonMatrix. """
import numpy as np

class ComparisonMatrix:
    def __init__(self, file_names: list[str]):
        self.names = file_names
        self.n = len(file_names)
        self.matrix = np.ones((self.n, self.n), dtype=np.float32)

    def set(self, i: int, j: int, score: float):
        self.matrix[i, j] = score
        self.matrix[j, i] = score

    def get(self, i: int, j: int) -> float:
        return float(self.matrix[i, j])

    def as_numpy(self) -> np.ndarray:
        return self.matrix

    def to_csv(self) -> str:
        lines = ["," + ",".join(self.names)]
        for i, name in enumerate(self.names):
            row = [name] + [f"{self.matrix[i, j]:.4f}" for j in range(self.n)]
            lines.append(",".join(row))
        return "\n".join(lines)

    def get_flagged(self, threshold: float) -> list[dict]:
        flagged = []
        for i in range(self.n):
            for j in range(i + 1, self.n):
                if self.matrix[i, j] >= threshold:
                    flagged.append({
                        "file_a": self.names[i],
                        "file_b": self.names[j],
                        "score": float(self.matrix[i, j])
                    })
        return flagged
