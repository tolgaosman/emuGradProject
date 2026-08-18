""" winnowing.py — Winnowing document fingerprinting. """
# Reference: Schleimer, Wilkerson & Aiken (ACM SIGMOD 2003).
import hashlib

from .base import SimilarityModel


def _h32(text: str) -> int:
    """Hash `text` to a 32-bit integer via SHA-256."""
    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32)


class WinnowingModel(SimilarityModel):
    """Winnowing document fingerprinting with k=5-gram hashing, w=4 window."""

    def __init__(self, k: int = 5, w: int = 4):
        """Set the k-gram size and winnowing window width."""
        self.k, self.w = k, w

    def fingerprint(self, tokens: list[str]) -> set[int]:
        """Compute the winnowing fingerprint set for `tokens`."""
        if len(tokens) < self.k:
            return set()
        kgrams = [" ".join(tokens[i : i + self.k]) for i in range(len(tokens) - self.k + 1)]
        hashes = [_h32(kg) for kg in kgrams]
        fps, prev = set(), -1
        for i in range(len(hashes) - self.w + 1):
            window = hashes[i : i + self.w]
            min_val = min(window)
            min_idx = i + window.index(min_val)
            if min_idx != prev:  # avoid duplicate minimum selection
                fps.add(min_val)
                prev = min_idx
        return fps

    def compute(self, tokens_a: list[str], tokens_b: list[str]) -> float:
        """Compute the Jaccard similarity of the two fingerprint sets."""
        fp_a, fp_b = self.fingerprint(tokens_a), self.fingerprint(tokens_b)
        if not fp_a or not fp_b:
            return 0.0
        return len(fp_a & fp_b) / len(fp_a | fp_b)
