""" test_ai_detector.py — AIDetector heuristic scoring, bands, segments. """
import pytest
from src.models.ai_detector import AIDetector


@pytest.fixture
def detector():
    return AIDetector()


def test_assess_text_empty_returns_low(detector):
    result = detector.assess_text("")
    assert result.overall_probability == 0.0
    assert result.band == "low"
    assert result.segments == []


def test_assess_text_returns_bounded_probability(detector):
    text = "This is a short, ordinary sentence. Here is another one, a bit different."
    result = detector.assess_text(text)
    assert 0.0 <= result.overall_probability <= 1.0
    assert result.band in ("low", "possible", "likely")


def test_assess_text_formal_hedge_heavy_scores_higher_than_casual(detector):
    """Directional check: heavy hedge-word usage + uniform sentences should
    score higher than casual, bursty, contraction-heavy prose."""
    casual = (
        "I didn't really expect this to work, honestly. But hey, it did! "
        "The trick was simple: don't overthink it. Sometimes the dumb "
        "solution is the right one, you know?"
    )
    formal = (
        "Furthermore, it is important to note that this approach yields "
        "significant benefits. Moreover, the implementation demonstrates "
        "consistent performance across various scenarios. Additionally, "
        "the results indicate a substantial improvement in efficiency."
    )
    casual_score = detector.compute_text_probability(casual)
    formal_score = detector.compute_text_probability(formal)
    assert formal_score > casual_score


def test_assess_text_segments_cover_every_sentence(detector):
    text = "First sentence here. Second sentence follows. Third one too."
    result = detector.assess_text(text)
    assert len(result.segments) == 3
    for segment in result.segments:
        assert 0.0 <= segment.probability <= 1.0
        assert segment.start < segment.end


def test_assess_text_never_claims_certainty(detector):
    """Scores stay clamped away from the extremes — a heuristic should
    never claim 0% or 100% confidence."""
    extreme = "Furthermore. Moreover. Additionally. Consequently. " * 20
    result = detector.assess_text(extreme)
    assert result.overall_probability <= 0.95
    assert result.overall_probability >= 0.05


def test_assess_code_empty_returns_low(detector):
    result = detector.assess_code("", "python")
    assert result.overall_probability == 0.0
    assert result.band == "low"


def test_assess_code_uses_python_comment_syntax(detector):
    code = "# this explains it\nx = 1\n# and this too\ny = 2\n"
    result = detector.assess_code(code, "python")
    comment_signal = next(s for s in result.signals if s.name == "comment_ratio")
    assert comment_signal.score > 0.15  # 2 of 3 non-blank lines are # comments


def test_assess_code_uses_c_family_comment_syntax_not_hash():
    """A Java file whose comments use // must not be scored as having zero
    comments just because it has no '#' lines."""
    detector = AIDetector()
    code = (
        "public class Main {\n"
        "    // this explains it\n"
        "    int x = 1;\n"
        "    // and this too\n"
        "    int y = 2;\n"
        "}\n"
    )
    result = detector.assess_code(code, "java")
    comment_signal = next(s for s in result.signals if s.name == "comment_ratio")
    assert comment_signal.score > 0.15


def test_assess_code_generic_identifiers_signal(detector):
    generic = "def f(data, result, temp):\n    result = data + temp\n    return result\n"
    specific = "def f(velocity, mass, friction):\n    force = mass * friction\n    return force\n"
    generic_signals = detector.assess_code(generic, "python").signals
    specific_signals = detector.assess_code(specific, "python").signals
    generic_score = next(s for s in generic_signals if s.name == "generic_identifiers").score
    specific_score = next(s for s in specific_signals if s.name == "generic_identifiers").score
    assert generic_score > specific_score


def test_assess_code_segments_nonempty_for_multiblock_source(detector):
    code = "int a = 1;\n\nint b = 2;\n\nint c = 3;\n"
    result = detector.assess_code(code, "c")
    assert len(result.segments) >= 1
    for segment in result.segments:
        assert 0.0 <= segment.probability <= 1.0


def test_band_thresholds():
    # Directly exercise the band boundaries via the module-level thresholds.
    from src.models.ai_detector import _band

    assert _band(0.0) == "low"
    assert _band(0.34) == "low"
    assert _band(0.35) == "possible"
    assert _band(0.64) == "possible"
    assert _band(0.65) == "likely"
    assert _band(1.0) == "likely"


def test_to_dict_shapes():
    detector = AIDetector()
    result = detector.assess_text("A reasonably ordinary sentence for testing purposes here.")
    body = result.to_dict()
    assert set(body.keys()) == {"overall_probability", "band", "signals", "segments"}
    assert isinstance(body["signals"], list)
    assert isinstance(body["segments"], list)
    if body["signals"]:
        assert set(body["signals"][0].keys()) == {"name", "score", "weight"}
    if body["segments"]:
        assert set(body["segments"][0].keys()) == {"start", "end", "probability"}
