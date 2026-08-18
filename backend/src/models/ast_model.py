""" ast_model.py — Python AST Comparison Model. """
import ast

import Levenshtein

from .base import SimilarityModel


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
