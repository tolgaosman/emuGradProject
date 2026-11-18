""" ast_model.py — Python AST Comparison Model & C-family structural normalizer. """
import ast
import re

import Levenshtein

from ..language import blank_comments_and_strings
from .base import SimilarityModel

#: Control-flow and primitive keywords preserved verbatim during C/C++/Java
#: structural normalization so control structure and types distinguish
#: unrelated functions while user-chosen names become positional `id_N` tokens.
_C_FAMILY_KEYWORDS = frozenset({
    "if", "else", "for", "while", "do", "switch", "case", "default",
    "break", "continue", "return", "try", "catch", "finally", "throw", "throws",
    "new", "delete", "sizeof", "true", "false", "null", "nullptr", "this", "super",
    "void", "int", "long", "short", "char", "float", "double", "bool", "boolean",
    "unsigned", "signed", "const", "static", "public", "private", "protected",
    "final", "class", "struct", "enum", "interface", "namespace", "template",
})

_NON_FUNC_HEADS = frozenset({"if", "for", "while", "switch", "catch", "synchronized", "return"})

_C_FUNC_HEAD_RE = re.compile(
    r"(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\b|noexcept\b|override\b|throws\s+[\w.,\s]+)*\{"
)

_C_STRUCT_TOKEN_RE = re.compile(
    r"\d+\.\d+|\d+|[A-Za-z_]\w*|==|!=|<=|>=|&&|\|\||\+\+|--|\+=|-=|\*=|/=|->|[{}()\[\];,+\-*/%<>!=&|^~?:]"
)

_MIN_C_FUNC_TOKENS = 12


def normalize_c_family_block(masked_block: str) -> tuple[str, int]:
    """Normalize a comment/string-blanked C/C++/Java block into canonical tokens.

    Returns `(canonical_signature, token_count)`. User identifiers become
    `id_0`, `id_1`, ... in order of first appearance within the block.
    """
    id_map: dict[str, str] = {}
    out: list[str] = []
    for match in _C_STRUCT_TOKEN_RE.finditer(masked_block):
        tok = match.group()
        first = tok[0]
        if first.isdigit():
            out.append("NUM")
        elif first.isalpha() or first == "_":
            if tok in _C_FAMILY_KEYWORDS:
                out.append(tok)
            else:
                mapped = id_map.get(tok)
                if mapped is None:
                    mapped = f"id_{len(id_map)}"
                    id_map[tok] = mapped
                out.append(mapped)
        else:
            out.append(tok)
    return " ".join(out), len(out)


def extract_c_family_functions(code: str, language: str) -> list[tuple[str, int, int]]:
    """Return `(canonical_signature, start, end)` for each function/method in `code`.

    Comments and string literals are blanked in place first so brace matching
    and tokenization ignore them while offsets still index into `code`.
    """
    masked = blank_comments_and_strings(code, language)
    out: list[tuple[str, int, int]] = []
    cursor = 0
    length = len(masked)

    while cursor < length:
        match = _C_FUNC_HEAD_RE.search(masked, cursor)
        if match is None:
            break
        name = match.group("name")
        brace_open = match.end() - 1
        if name in _NON_FUNC_HEADS:
            cursor = match.start() + len(name)
            continue

        # Walk back to include the return type / modifiers on this declaration.
        decl_start = match.start()
        while decl_start > 0 and masked[decl_start - 1] not in ";{}":
            decl_start -= 1
        while decl_start < match.start() and masked[decl_start].isspace():
            decl_start += 1

        depth = 1
        pos = brace_open + 1
        while pos < length and depth > 0:
            ch = masked[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            pos += 1

        if depth != 0:
            break

        sig, tok_count = normalize_c_family_block(masked[decl_start:pos])
        if tok_count >= _MIN_C_FUNC_TOKENS:
            out.append((sig, decl_start, pos))
        cursor = pos

    return out


class _NormalizerNodeVisitor(ast.NodeVisitor):
    """Renames identifiers/functions/classes to positional placeholders.

    This strips surface-level renaming (e.g. `total` -> `sum_val`) from the
    AST so structurally identical code compares as identical regardless of
    what the author called their variables, functions, classes, or
    attributes.
    """

    def __init__(self):
        self.var_count = 0
        self.func_count = 0
        self.class_count = 0
        self.var_map: dict[str, str] = {}
        self.func_map: dict[str, str] = {}
        self.class_map: dict[str, str] = {}

    def visit_Name(self, node: ast.Name) -> None:
        node.id = self._normalize(node.id, self.var_map, "var")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        node.name = self._normalize(node.name, self.func_map, "func")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        node.name = self._normalize(node.name, self.func_map, "func")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        node.name = self._normalize(node.name, self.class_map, "class")
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        node.arg = self._normalize(node.arg, self.var_map, "var")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        node.attr = self._normalize(node.attr, self.var_map, "var")
        self.generic_visit(node)

    def _normalize(self, name: str, mapping: dict[str, str], prefix: str) -> str:
        if name not in mapping:
            count = getattr(self, f"{prefix}_count")
            mapping[name] = f"{prefix}_{count}"
            setattr(self, f"{prefix}_count", count + 1)
        return mapping[name]


class ASTModel(SimilarityModel):
    """Structural similarity via normalized AST node-sequence Levenshtein distance.

    `tokens_a`/`tokens_b` are expected to each contain the raw Python source
    as a single-element list (the engine passes `[raw_source]` rather than
    prose tokens here, since AST parsing needs the original punctuation that
    the NLP preprocessor strips).
    """

    def compute(self, tokens_a: list[str], tokens_b: list[str]) -> float:
        """Parse both sources, normalize identifiers, and diff the ASTs."""
        code_a = "\n".join(tokens_a)
        code_b = "\n".join(tokens_b)

        try:
            tree_a = ast.parse(code_a)
            tree_b = ast.parse(code_b)
        except (SyntaxError, ValueError, RecursionError):
            return 0.0

        _NormalizerNodeVisitor().visit(tree_a)
        _NormalizerNodeVisitor().visit(tree_b)

        dump_a = ast.dump(tree_a)
        dump_b = ast.dump(tree_b)

        distance = Levenshtein.distance(dump_a, dump_b)
        max_len = max(len(dump_a), len(dump_b))

        if max_len == 0:
            return 1.0

        return float(1.0 - (distance / max_len))
