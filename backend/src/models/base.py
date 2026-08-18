""" base.py — Abstract SimilarityModel interface. """
from abc import ABC, abstractmethod


class SimilarityModel(ABC):
    """Common interface implemented by every similarity engine."""

    @abstractmethod
    def compute(self, tokens_a: list[str], tokens_b: list[str]) -> float:
        """Compute a similarity score between two token lists.

        Args:
            tokens_a: List of strings.
            tokens_b: List of strings.

        Returns:
            Float between 0.0 and 1.0.

        """
