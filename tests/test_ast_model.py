""" test_ast_model.py — ASTModel (normalized Python AST comparison). """
import pytest
from src.models.ast_model import ASTModel


@pytest.fixture
def model():
    return ASTModel()


def _src(code: str) -> list[str]:
    # The model joins the list with newlines, so split source into lines.
    return code.strip("\n").split("\n")


def test_tc15_identical_code_one(model):
    """TC-15: identical source code yields similarity 1.0."""
    code = _src(
        """
def add(a, b):
    result = a + b
    return result
"""
    )
    assert model.compute(code, list(code)) == pytest.approx(1.0)


def test_tc16_variable_rename_invariance(model):
    """TC-16: renaming identifiers keeps similarity high (AST normalizes names)."""
    code_a = _src(
        """
def add(a, b):
    result = a + b
    return result
"""
    )
    code_b = _src(
        """
def sum_values(x, y):
    total = x + y
    return total
"""
    )
    score = model.compute(code_a, code_b)
    assert score == pytest.approx(1.0)


def test_tc17_syntax_error_zero(model):
    """TC-17: unparseable code yields 0.0."""
    bad = ["def broken(:", "    return"]
    good = _src("def ok():\n    return 1")
    assert model.compute(bad, good) == 0.0


def test_class_rename_invariance(model):
    """Renaming a class keeps similarity high (AST normalizes class names)."""
    code_a = _src(
        """
class Adder:
    def add(self, a, b):
        return a + b
"""
    )
    code_b = _src(
        """
class Summer:
    def add(self, a, b):
        return a + b
"""
    )
    assert model.compute(code_a, code_b) == pytest.approx(1.0)


def test_attribute_rename_invariance(model):
    """Renaming an attribute keeps similarity high (AST normalizes attrs)."""
    code_a = _src(
        """
class Box:
    def get(self):
        return self.value
"""
    )
    code_b = _src(
        """
class Box:
    def get(self):
        return self.contents
"""
    )
    assert model.compute(code_a, code_b) == pytest.approx(1.0)


def test_null_byte_source_returns_zero(model):
    """Source that raises ValueError on parse (e.g. embedded null bytes)
    yields 0.0 instead of propagating the exception."""
    bad = ["a = 1\x00"]
    good = _src("a = 1")
    assert model.compute(bad, good) == 0.0
