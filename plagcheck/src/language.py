""" language.py — Single source of truth for language/mode concerns.

Nothing outside this module should hard-code a file extension, a per-mode
allow-list, or a language's comment syntax — loader, preprocessor, engine,
and the AI detector all import from here so the four supported languages
(prose "text", python, java, c, cpp) stay consistent across the pipeline.
"""
import re

#: Maps a lowercase file extension to the language it represents.
EXT_TO_LANGUAGE: dict[str, str] = {
    ".txt": "text",
    ".pdf": "text",
    ".docx": "text",
    ".py": "python",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
}

#: The four user-facing scanning modes.
MODES = {"code_similarity", "text_similarity", "ai_code", "ai_text"}

#: Which extensions each mode accepts, per the product spec: text modes take
#: .txt/.pdf/.docx, code modes take .py/.java/.c/.cpp.
_TEXT_EXTENSIONS = {".txt", ".pdf", ".docx"}
_CODE_EXTENSIONS = {".py", ".java", ".c", ".h", ".cpp", ".cc", ".hpp"}

MODE_EXTENSIONS: dict[str, set[str]] = {
    "text_similarity": _TEXT_EXTENSIONS,
    "ai_text": _TEXT_EXTENSIONS,
    "code_similarity": _CODE_EXTENSIONS,
    "ai_code": _CODE_EXTENSIONS,
}

#: (line-comment prefix, block-comment start, block-comment end) per language.
#: `None` for a slot means that language has no such construct.
COMMENT_SYNTAX: dict[str, tuple[str | None, str | None, str | None]] = {
    "python": ("#", '"""', '"""'),
    "java": ("//", "/*", "*/"),
    "c": ("//", "/*", "*/"),
    "cpp": ("//", "/*", "*/"),
    "text": (None, None, None),
}

CODE_LANGUAGES = {"python", "java", "c", "cpp"}


def language_for_extension(ext: str) -> str | None:
    """Return the language for a lowercase extension (with leading dot).

    Returns None if it isn't recognized.
    """
    return EXT_TO_LANGUAGE.get(ext.lower())


def is_allowed_for_mode(ext: str, mode: str) -> bool:
    """Return whether `ext` (lowercase, with leading dot) is accepted by `mode`."""
    allowed = MODE_EXTENSIONS.get(mode)
    return allowed is not None and ext.lower() in allowed


def line_comment_prefix(language: str) -> str | None:
    """Return the line-comment prefix for `language`, or None if it has none."""
    return COMMENT_SYNTAX.get(language, (None, None, None))[0]


def strip_comments_and_strings(text: str, language: str) -> str:
    """Remove comments and string literals from `text` for `language`.

    Used by both the code tokenizer and the AI-detector's structural signals
    so line-length/uniformity measurements aren't skewed by long string
    literals or comment text. Python is intentionally excluded — its own
    `tokenize`-based path already separates comments/strings without regex.
    """
    line_cm, block_start, block_end = COMMENT_SYNTAX.get(language, (None, None, None))
    out = text

    # String/char literals first, so a comment marker inside a string isn't
    # mistaken for the start of a real comment.
    out = re.sub(r'"(?:\\.|[^"\\])*"', '""', out)
    out = re.sub(r"'(?:\\.|[^'\\])*'", "''", out)

    if block_start and block_end:
        out = re.sub(re.escape(block_start) + r".*?" + re.escape(block_end), "", out, flags=re.S)
    if line_cm:
        out = re.sub(re.escape(line_cm) + r".*", "", out)

    return out


# --------------------------------------------------------------------------
# Language detection for the paste box (heuristic keyword/syntax scoring).
# --------------------------------------------------------------------------

_SIGNATURES: dict[str, list[re.Pattern]] = {
    "python": [
        re.compile(r"\bdef\s+\w+\s*\("),
        re.compile(r"\bimport\s+\w"),
        re.compile(r"\bself\b"),
        re.compile(r":\s*$", re.M),
        re.compile(r"\belif\b"),
        re.compile(r"\bNone\b|\bTrue\b|\bFalse\b"),
    ],
    "java": [
        re.compile(r"\bpublic\s+(static\s+)?(class|void|final)\b"),
        re.compile(r"\bSystem\.out\.println\b"),
        re.compile(r"\bnew\s+\w+\s*\("),
        re.compile(r"\bimport\s+java\."),
        re.compile(r"\bprivate\b|\bprotected\b"),
        re.compile(r";\s*$", re.M),
    ],
    "c": [
        re.compile(r"#include\s*<\w+\.h>"),
        re.compile(r"\bprintf\s*\("),
        re.compile(r"\bmalloc\s*\(|\bfree\s*\("),
        re.compile(r"\bstruct\s+\w+"),
        re.compile(r"\bint\s+main\s*\("),
    ],
    "cpp": [
        re.compile(r"#include\s*<\w+>"),
        re.compile(r"\bstd::"),
        re.compile(r"\bcout\b|\bcin\b"),
        re.compile(r"\btemplate\s*<"),
        re.compile(r"\bclass\s+\w+.*\{"),
        re.compile(r"\bnamespace\s+\w+"),
    ],
}


def detect_language(source: str) -> tuple[str, float]:
    """Guess which of python/java/c/cpp `source` is written in.

    Returns (language, confidence) where confidence is the winning language's
    share of all signature hits across all languages, in [0.0, 1.0]. Falls
    back to ("python", 0.0) for empty or entirely ambiguous input — an
    explicit low-confidence result the caller/UI should treat as "ask the
    user", not a real guess.
    """
    if not source.strip():
        return "python", 0.0

    scores = {
        lang: sum(1 for pat in pats if pat.search(source)) for lang, pats in _SIGNATURES.items()
    }
    total = sum(scores.values())
    if total == 0:
        return "python", 0.0

    best_lang = max(scores, key=lambda lang: scores[lang])
    confidence = scores[best_lang] / total
    return best_lang, confidence
