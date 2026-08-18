""" matrix.py — ComparisonMatrix. """
import csv
import io

import numpy as np


class ComparisonMatrix:
    """A symmetric float32 similarity matrix over a batch of files."""

    def __init__(self, file_names: list[str]):
        """Initialize an n x n matrix (diagonal = 1.0) for `file_names`."""
        self.names = file_names
        self.n = len(file_names)
        self.matrix = np.ones((self.n, self.n), dtype=np.float32)

    def set(self, i: int, j: int, score: float) -> None:
        """Set the similarity score for pair (i, j), mirrored to (j, i)."""
        self.matrix[i, j] = score
        self.matrix[j, i] = score

    def get(self, i: int, j: int) -> float:
        """Return the similarity score for pair (i, j)."""
        return float(self.matrix[i, j])

    def as_numpy(self) -> np.ndarray:
        """Return the underlying numpy array."""
        return self.matrix

    def to_csv(self) -> str:
        """Render the matrix as a CSV string with a header row/column.

        Written through `csv.writer` rather than joining on commas: file
        names are original upload names, so one containing a comma or quote
        would otherwise shift every column in that row.
        """
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow([""] + self.names)
        for i, name in enumerate(self.names):
            writer.writerow([name] + [f"{self.matrix[i, j]:.4f}" for j in range(self.n)])
        return buf.getvalue().rstrip("\n")

    def all_pairs(self) -> list[dict]:
        """Return every unique (file_a, file_b, score) pair, unfiltered."""
        return [
            {"file_a": self.names[i], "file_b": self.names[j], "score": float(self.matrix[i, j])}
            for i in range(self.n)
            for j in range(i + 1, self.n)
        ]

    def get_flagged(self, threshold: float) -> list[dict]:
        """Return every unique pair whose score meets `threshold`."""
        return [pair for pair in self.all_pairs() if pair["score"] >= threshold]
