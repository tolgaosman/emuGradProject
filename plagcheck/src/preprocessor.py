""" preprocessor.py — NLP Preprocessor. """
import io
import os
import re
import tokenize as py_tokenize
from tokenize import TokenError

from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from nltk.tokenize import word_tokenize

# Token types worth keeping when tokenizing Python source: identifiers,
# keywords, and literals. Comments, whitespace, and punctuation carry no
# similarity signal and are dropped, mirroring the prose pipeline's
# punctuation-stripping step.
_PY_KEEP_TYPES = {py_tokenize.NAME, py_tokenize.NUMBER, py_tokenize.STRING}

# Default location of the academic exclusion list. The CLI is launched from
# inside plagcheck/, so config/ lives one directory above the package root:
#   <repo_root>/config/exclusions.txt  ==  <this file>/../../config/exclusions.txt
_DEFAULT_EXCLUSIONS = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "exclusions.txt"
)


class Preprocessor:
    """The 6-step NLP pipeline.

    Lowercase, strip punctuation, tokenize, remove stopwords/exclusions,
    stem, and generate k-grams.
    """

    def __init__(self, k: int = 5, exclusions_path: str | None = None):
        """Build the stemmed stopword set (NLTK + `config/exclusions.txt`)."""
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

    def process(self, text: str, is_python: bool = False) -> tuple[list[str], list[str]]:
        """Run the NLP pipeline over `text`, returning (tokens, k-grams).

        Prose text is lowercased, stripped of punctuation, and word-tokenized
        via NLTK. Python source (`is_python=True`) is instead tokenized with
        the standard-library `tokenize` module so identifiers/keywords/
        literals are preserved and code punctuation isn't mistaken for prose
        noise; it falls back to the prose path if the source fails to
        tokenize (e.g. a syntax error).
        """
        raw_tokens = self._tokenize_python(text) if is_python else None
        if raw_tokens is None:
            raw_tokens = self._tokenize_prose(text)

        tokens = [
            stemmed
            for t in raw_tokens
            if (stemmed := self.stemmer.stem(t)) not in self.stop_words
        ]

        kgrams = []
        if len(tokens) >= self.k:
            kgrams = [" ".join(tokens[i : i + self.k]) for i in range(len(tokens) - self.k + 1)]

        return tokens, kgrams

    def _tokenize_prose(self, text: str) -> list[str]:
        """Lowercase, strip punctuation, and word-tokenize prose text."""
        text = text.lower()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()

        try:
            return word_tokenize(text)
        except LookupError:
            import nltk

            nltk.download("punkt")
            nltk.download("punkt_tab")
            return word_tokenize(text)

    def _tokenize_python(self, text: str) -> list[str] | None:
        """Tokenize Python source into lowercased identifier/literal tokens.

        Returns None (triggering a fall back to prose tokenization) if the
        source cannot be tokenized, e.g. it contains a syntax error.
        """
        try:
            tokens = py_tokenize.generate_tokens(io.StringIO(text).readline)
            return [tok.string.lower() for tok in tokens if tok.type in _PY_KEEP_TYPES]
        except (TokenError, IndentationError, SyntaxError):
            return None
