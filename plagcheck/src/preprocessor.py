""" preprocessor.py — NLP Preprocessor. """
import re
# pyrefly: ignore [missing-import]
from nltk.tokenize import word_tokenize
# pyrefly: ignore [missing-import]
from nltk.corpus import stopwords
# pyrefly: ignore [missing-import]
from nltk.stem import PorterStemmer

class Preprocessor:
    def __init__(self, k: int = 5):
        self.k = k
        try:
            self.stop_words = set(stopwords.words("english"))
        except LookupError:
            # pyrefly: ignore [missing-import]
            import nltk
            nltk.download("punkt")
            nltk.download("stopwords")
            self.stop_words = set(stopwords.words("english"))
            
        self.stemmer = PorterStemmer()
        
    def process(self, text: str, is_python: bool = False) -> tuple[list[str], list[str]]:  # noqa: ARG002
        text = text.lower()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        
        try:
            tokens = word_tokenize(text)
        except LookupError:
            # pyrefly: ignore [missing-import]
            import nltk
            nltk.download("punkt")
            nltk.download("punkt_tab")
            tokens = word_tokenize(text)
            
        tokens = [self.stemmer.stem(t) for t in tokens if t not in self.stop_words]
        
        kgrams = []
        if len(tokens) >= self.k:
            kgrams = [" ".join(tokens[i:i+self.k]) for i in range(len(tokens)-self.k+1)]
            
        return tokens, kgrams
