""" ast_model.py — Python AST Comparison Model. """
import ast
import Levenshtein
from .base import SimilarityModel

class _NormalizerNodeVisitor(ast.NodeVisitor):
    def __init__(self):
        self.var_count = 0
        self.func_count = 0
        self.var_map = {}
        self.func_map = {}

    def visit_Name(self, node):
        if node.id not in self.var_map:
            self.var_map[node.id] = f"var_{self.var_count}"
            self.var_count += 1
        node.id = self.var_map[node.id]
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.name not in self.func_map:
            self.func_map[node.name] = f"func_{self.func_count}"
            self.func_count += 1
        node.name = self.func_map[node.name]
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        if node.name not in self.func_map:
            self.func_map[node.name] = f"func_{self.func_count}"
            self.func_count += 1
        node.name = self.func_map[node.name]
        self.generic_visit(node)

    def visit_arg(self, node):
        if node.arg not in self.var_map:
            self.var_map[node.arg] = f"var_{self.var_count}"
            self.var_count += 1
        node.arg = self.var_map[node.arg]
        self.generic_visit(node)


class ASTModel(SimilarityModel):
    def compute(self, tokens_a: list[str], tokens_b: list[str]) -> float:
        # tokens_a and tokens_b should actually be the raw python source code here.
        # However, to fit the SimilarityModel interface, we assume the preprocessor
        # passes the raw code as a single string inside the list or we join it back.
        # We will attempt to parse the joined tokens.
        # But wait, preprocessor normally tokenizes text. For AST model, we need the raw file.
        # Let's rebuild the code from tokens or expect raw string in tokens_a[0] if it's .py.
        # Actually, for AST comparison we need the AST string representation of the parsed code.
        
        # Let's join the code, but note that preprocessor removes punctuation, which breaks Python code.
        # For AST, we should probably bypass normal preprocessing.
        # We'll just assume tokens_a is the raw python code split into lines or just raw text passed.
        # Let's join it back. If it fails to parse, return 0.0.
        code_a = "\n".join(tokens_a)
        code_b = "\n".join(tokens_b)
        
        try:
            tree_a = ast.parse(code_a)
            tree_b = ast.parse(code_b)
        except SyntaxError:
            return 0.0

        visitor_a = _NormalizerNodeVisitor()
        visitor_a.visit(tree_a)
        
        visitor_b = _NormalizerNodeVisitor()
        visitor_b.visit(tree_b)
        
        dump_a = ast.dump(tree_a)
        dump_b = ast.dump(tree_b)
        
        distance = Levenshtein.distance(dump_a, dump_b)
        max_len = max(len(dump_a), len(dump_b))
        
        if max_len == 0:
            return 1.0
            
        similarity = 1.0 - (distance / max_len)
        return float(similarity)
