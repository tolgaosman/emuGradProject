""" cosine.py — TF-IDF Cosine Similarity Model. """
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .base import SimilarityModel

class CosineModel(SimilarityModel):
    def compute(self, tokens_a: list[str], tokens_b: list[str]) -> float:
        if not tokens_a or not tokens_b:
            return 0.0
            
        text_a = " ".join(tokens_a)
        text_b = " ".join(tokens_b)
        
        vectorizer = TfidfVectorizer()
        try:
            tfidf_matrix = vectorizer.fit_transform([text_a, text_b])
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])
            return float(similarity[0][0])
        except ValueError: # Empty vocabulary usually
            return 0.0
