""" preprocessor.py — NLP Preprocessor. """
import re
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer

class Preprocessor:
    def __init__(self, k: int = 5):
        self.k = k
        try:
            self.stop_words = set(stopwords.words("english"))
        except LookupError:
            import nltk
            nltk.download("punkt")
            nltk.download("stopwords")
            self.stop_words = set(stopwords.words("english"))
            
        self.stemmer = PorterStemmer()
        
    def process(self, text: str, is_python: bool = False) -> tuple[list[str], list[str]]:
        if is_python:
            # For python code, we return the raw code as a list of lines so AST model can use it.
            # But we also want to return tokens for other models if 'all' is selected.
            # The prompt says: Return: Tuple of `(tokens: list[str], kgrams: list[str])`.
            # Let's standardise on passing the raw code for AST, but for normal NLP, we do standard pipeline.
            # We can just return the raw text as a single token list `[text]` if it's python and we just want AST?
            # Or we do both. Let's do standard NLP pipeline, but AST needs raw text.
            # Actually, `engine.py` might pass raw text to AST model directly if it knows it.
            # Let's keep `process` returning NLP tokens and kgrams.
            pass

        text = text.lower()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        
        try:
            tokens = word_tokenize(text)
        except LookupError:
            import nltk
            nltk.download("punkt")
            nltk.download("punkt_tab")
            tokens = word_tokenize(text)
            
        tokens = [self.stemmer.stem(t) for t in tokens if t not in self.stop_words]
        
        kgrams = []
        if len(tokens) >= self.k:
            kgrams = [" ".join(tokens[i:i+self.k]) for i in range(len(tokens)-self.k+1)]
            
        return tokens, kgrams
