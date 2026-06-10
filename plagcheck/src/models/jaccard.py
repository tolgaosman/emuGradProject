""" jaccard.py — Jaccard Index Similarity Model. """
from .base import SimilarityModel

class JaccardModel(SimilarityModel):
    def compute(self, tokens_a: list[str], tokens_b: list[str]) -> float:
        set_a = set(tokens_a)
        set_b = set(tokens_b)
        
        if not set_a or not set_b:
            return 0.0
            
        intersection = len(set_a.intersection(set_b))
        union = len(set_a.union(set_b))
        
        return float(intersection / union)
