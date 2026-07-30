""" test_language.py — language detection, mode allow-lists, comment syntax. """
from src.language import (
    detect_language,
    is_allowed_for_mode,
    language_for_extension,
    line_comment_prefix,
    strip_comments_and_strings,
)


def test_language_for_extension_maps_all_supported_extensions():
    assert language_for_extension(".txt") == "text"
    assert language_for_extension(".pdf") == "text"
    assert language_for_extension(".docx") == "text"
    assert language_for_extension(".py") == "python"
    assert language_for_extension(".java") == "java"
    assert language_for_extension(".c") == "c"
    assert language_for_extension(".cpp") == "cpp"


def test_language_for_extension_unknown_returns_none():
    assert language_for_extension(".exe") is None


def test_is_allowed_for_mode_text_modes_reject_code():
    assert is_allowed_for_mode(".txt", "text_similarity") is True
    assert is_allowed_for_mode(".py", "text_similarity") is False
    assert is_allowed_for_mode(".txt", "ai_text") is True
    assert is_allowed_for_mode(".java", "ai_text") is False


def test_is_allowed_for_mode_code_modes_reject_text():
    assert is_allowed_for_mode(".py", "code_similarity") is True
    assert is_allowed_for_mode(".java", "code_similarity") is True
    assert is_allowed_for_mode(".c", "ai_code") is True
    assert is_allowed_for_mode(".docx", "code_similarity") is False


def test_line_comment_prefix_python_vs_c_family():
    assert line_comment_prefix("python") == "#"
    assert line_comment_prefix("java") == "//"
    assert line_comment_prefix("c") == "//"
    assert line_comment_prefix("cpp") == "//"
    assert line_comment_prefix("text") is None


def test_strip_comments_and_strings_removes_line_comment():
    result = strip_comments_and_strings("int x = 1; // set x\nint y = 2;", "c")
    assert "set x" not in result
    assert "int y = 2" in result


def test_strip_comments_and_strings_removes_block_comment():
    result = strip_comments_and_strings("int x = 1; /* explanation */ int y = 2;", "java")
    assert "explanation" not in result
    assert "int y = 2" in result


def test_strip_comments_and_strings_removes_string_contents():
    result = strip_comments_and_strings('char *s = "// not a comment";', "c")
    assert "not a comment" not in result


def test_detect_language_python():
    code = "def add(a, b):\n    return a + b\n\nif __name__ == '__main__':\n    print(add(1, 2))\n"
    lang, confidence = detect_language(code)
    assert lang == "python"
    assert confidence > 0.5


def test_detect_language_java():
    code = (
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        System.out.println(new Main());\n"
        "    }\n"
        "}\n"
    )
    lang, confidence = detect_language(code)
    assert lang == "java"
    assert confidence > 0.5


def test_detect_language_c():
    code = "#include <stdio.h>\nint main() {\n    printf(\"hi\");\n    return 0;\n}\n"
    lang, confidence = detect_language(code)
    assert lang == "c"


def test_detect_language_cpp():
    code = (
        "#include <iostream>\n"
        "using namespace std;\n"
        "template<typename T>\n"
        "class Box { public: T value; };\n"
        "int main() { std::cout << \"hi\"; }\n"
    )
    lang, confidence = detect_language(code)
    assert lang == "cpp"


def test_detect_language_empty_returns_zero_confidence():
    lang, confidence = detect_language("   ")
    assert confidence == 0.0


def test_detect_language_ambiguous_returns_zero_confidence():
    """Plain English prose has none of the code signatures."""
    lang, confidence = detect_language("The weather today is quite pleasant and sunny.")
    assert confidence == 0.0
