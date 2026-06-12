""" preprocessor.py — NLP Preprocessor. """
import os
import re
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer

# Default location of the academic exclusion list. The CLI is launched from
# inside plagcheck/, so config/ lives one directory above the package root:
#   <repo_root>/config/exclusions.txt  ==  <this file>/../../config/exclusions.txt
_DEFAULT_EXCLUSIONS = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "exclusions.txt"
)


class Preprocessor:
    def __init__(self, k: int = 5, exclusions_path: str | None = None):
        self.k = k
        self.stemmer = PorterStemmer()

        try:
            raw_stopwords = set(stopwords.words("english"))
        except LookupError:
            import nltk
            nltk.download("punkt")
            nltk.download("stopwords")
            raw_stopwords = set(stopwords.words("english"))

        # Tokens are stemmed before they are compared against the stopword set,
        # so the stopword set must be stemmed too for the comparison to match.
        self.stop_words = {self.stemmer.stem(w) for w in raw_stopwords}

        # Merge in the academic / template exclusion terms (also stemmed).
        self.stop_words |= self._load_exclusions(exclusions_path)

    def _load_exclusions(self, exclusions_path: str | None) -> set[str]:
        path = (
            exclusions_path
            or os.environ.get("EXCLUSIONS_PATH")
            or _DEFAULT_EXCLUSIONS
        )
        if not path or not os.path.isfile(path):
            return set()

        terms: set[str] = set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                term = line.strip().lower()
                if not term or term.startswith("#"):
                    continue
                # Stem each whitespace-separated token so multi-word entries
                # still contribute their individual tokens to the filter.
                for token in term.split():
                    terms.add(self.stemmer.stem(token))
        return terms

    def process(self, text: str, is_python: bool = False) -> tuple[list[str], list[str]]:  # noqa: ARG002
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

        tokens = [
            stemmed
            for t in tokens
            if (stemmed := self.stemmer.stem(t)) not in self.stop_words
        ]

        kgrams = []
        if len(tokens) >= self.k:
            kgrams = [" ".join(tokens[i:i+self.k]) for i in range(len(tokens)-self.k+1)]

        return tokens, kgrams
