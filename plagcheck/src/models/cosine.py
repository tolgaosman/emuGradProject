""" cosine.py — TF-IDF Cosine Similarity Model. """
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .base import SimilarityModel


class CosineModel(SimilarityModel):
    """TF-IDF vectorization with cosine similarity, via scikit-learn."""

    def compute(self, tokens_a: list[str], tokens_b: list[str]) -> float:
        """Compute the TF-IDF cosine similarity between two token lists."""
        if not tokens_a or not tokens_b:
            return 0.0

        text_a = " ".join(tokens_a)
        text_b = " ".join(tokens_b)

        vectorizer = TfidfVectorizer()
        try:
            tfidf_matrix = vectorizer.fit_transform([text_a, text_b])
            # Compare the full pair matrix rather than slicing it (fit_transform
            # is typed as the abstract `spmatrix`, which has no __getitem__ even
            # though the concrete csr_matrix supports it at runtime).
            similarity = cosine_similarity(tfidf_matrix)
            return float(similarity[0][1])
        except ValueError:  # Empty vocabulary usually
            return 0.0
