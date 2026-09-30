""" preprocessor.py — NLP Preprocessor. """
import io
import logging
import os
import re
import tokenize as py_tokenize
from tokenize import TokenError

import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from nltk.tokenize import word_tokenize

from .language import strip_comments_and_strings

logger = logging.getLogger(__name__)

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

#: NLTK data (English stopwords + punkt_tab) ships with the repo so the
#: pipeline never reaches the network — the project is local-execution only.
NLTK_DATA_DIR = os.path.join(_BACKEND_DIR, "nltk_data")
if NLTK_DATA_DIR not in nltk.data.path:
    nltk.data.path.insert(0, NLTK_DATA_DIR)

# Token types worth keeping when tokenizing Python source: identifiers,
# keywords, and literals. Comments, whitespace, and punctuation carry no
# similarity signal and are dropped, mirroring the prose pipeline's
# punctuation-stripping step.
_PY_KEEP_TYPES = {py_tokenize.NAME, py_tokenize.NUMBER, py_tokenize.STRING}

#: Non-Python code languages handled by the generic regex tokenizer.
_GENERIC_CODE_LANGUAGES = {"java", "c", "cpp"}

#: Identifiers/keywords and numeric literals, applied after comments and
#: string literals have been stripped via `language.strip_comments_and_strings`.
_CODE_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|\d+\.\d+|\d+")

#: Academic / template term exclusion list (FR-15), `backend/config/`.
_DEFAULT_EXCLUSIONS = os.path.join(_BACKEND_DIR, "config", "exclusions.txt")


def _english_stopwords() -> set[str]:
    """Return NLTK's English stopword list, or an empty set if it is missing.

    Never downloads: a missing corpus degrades filtering, it doesn't fail the
    scan or reach the network.
    """
    try:
        return set(stopwords.words("english"))
    except LookupError:
        logger.warning("NLTK stopwords not found under %s; stopword removal is off.", NLTK_DATA_DIR)
        return set()


class Preprocessor:
    """The 6-step NLP pipeline.

    Lowercase, strip punctuation, tokenize, remove stopwords/exclusions,
    stem, and generate k-grams.
    """

    def __init__(self, k: int = 5, exclusions_path: str | None = None):
        """Build the stemmed stopword set and the stemmed exclusion set."""
        self.k = k
        self.stemmer = PorterStemmer()
        # Tokens are stemmed before they are compared against these sets, so
        # the sets must be stemmed too for the comparison to match.
        self.stop_words = {self.stemmer.stem(w) for w in _english_stopwords()}
        self.exclusions = self._load_exclusions(exclusions_path)

    def is_filtered(self, stemmed: str, language: str = "text") -> bool:
        """Whether a stemmed token is dropped from similarity computation.

        Stopwords apply everywhere. The exclusion list holds academic
        boilerplate ("abstract", "method", "result", ...) and applies to
        prose only — in source code those same words are ordinary
        identifiers, and dropping them would erase real structure. Span
        matching (`reporter._spanned_tokens`) uses this same predicate so
        highlighting and scoring always agree.
        """
        if stemmed in self.stop_words:
            return True
        return language == "text" and stemmed in self.exclusions

    def _load_exclusions(self, exclusions_path: str | None) -> set[str]:
        path = (
            exclusions_path
            or os.environ.get("EXCLUSIONS_PATH")
            or os.environ.get("EXCLUSION_LIST_PATH")
            or _DEFAULT_EXCLUSIONS
        )
        if not os.path.isfile(path):
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

    def process(self, text: str, language: str = "text") -> tuple[list[str], list[str]]:
        """Run the NLP pipeline over `text`, returning (tokens, k-grams).

        Prose text (`language="text"`) is lowercased, stripped of
        punctuation, and word-tokenized via NLTK. Python source
        (`language="python"`) is instead tokenized with the standard-library
        `tokenize` module so identifiers/keywords/literals are preserved and
        code punctuation isn't mistaken for prose noise; it falls back to
        the prose path if the source fails to tokenize (e.g. a syntax
        error). Java/C/C++ (`language in {"java","c","cpp"}`) use a generic
        regex tokenizer that strips comments/string literals first, since
        Python's `tokenize` module only understands Python syntax.
        """
        if language == "python":
            raw_tokens = self._tokenize_python(text)
        elif language in _GENERIC_CODE_LANGUAGES:
            raw_tokens = self._tokenize_code(text, language)
        else:
            raw_tokens = None

        if raw_tokens is None:
            raw_tokens = self._tokenize_prose(text)

        tokens = [
            stemmed
            for t in raw_tokens
            if not self.is_filtered(stemmed := self.stemmer.stem(t), language)
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
            # Punctuation is already stripped, so whitespace splitting yields
            # the same tokens punkt would; it just can't be as clever.
            logger.warning("NLTK punkt_tab not found under %s; splitting on spaces.", NLTK_DATA_DIR)
            return text.split()

    def _tokenize_code(self, text: str, language: str) -> list[str] | None:
        """Tokenize Java/C/C++ source into lowercased identifier/number tokens.

        Comments and string/char literals are stripped first (their content
        is irrelevant to structural similarity and can trigger false
        matches), then identifiers, keywords, and numeric literals are
        extracted via regex. Returns None (falling back to prose
        tokenization) if nothing survives.
        """
        stripped = strip_comments_and_strings(text, language)
        tokens = _CODE_TOKEN_RE.findall(stripped)
        return [t.lower() for t in tokens] if tokens else None

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
