""" winnowing.py — Winnowing document fingerprinting. """ 
# Reference: Schleimer, Wilkerson & Aiken (ACM SIGMOD 2003). 
import hashlib 
from .base import SimilarityModel 

def _h32(text: str) -> int: 
    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32) 

class WinnowingModel(SimilarityModel): 
    def __init__(self, k: int = 5, w: int = 4): 
        self.k, self.w = k, w 

    def fingerprint(self, tokens: list[str]) -> set[int]: 
        if len(tokens) < self.k: return set() 
        kgrams = [" ".join(tokens[i:i+self.k]) for i in range(len(tokens)-self.k+1)] 
        hashes = [_h32(kg) for kg in kgrams] 
        fps, prev = set(), -1 
        for i in range(len(hashes) - self.w + 1): 
            win = hashes[i : i+self.w] 
            mv = min(win) 
            mi = i + win.index(mv) 
            if mi != prev: # avoid duplicate minimum selection 
                fps.add(mv) 
                prev = mi 
        return fps 

    def compute(self, tokens_a, tokens_b) -> float: 
        fa, fb = self.fingerprint(tokens_a), self.fingerprint(tokens_b) 
        if not fa or not fb: return 0.0 
        return len(fa & fb) / len(fa | fb) 
