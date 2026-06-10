""" base.py — Abstract SimilarityModel interface. """
from abc import ABC, abstractmethod

class SimilarityModel(ABC):
    @abstractmethod
    def compute(self, tokens_a: list[str], tokens_b: list[str]) -> float:
        """
        Compute similarity score between two lists of tokens.
        
        Args:
            tokens_a: List of strings.
            tokens_b: List of strings.
            
        Returns:
            Float between 0.0 and 1.0.
        """
        pass
