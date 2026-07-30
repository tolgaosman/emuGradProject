""" engine.py — ScanEngine: orchestrates the four scanning modes. """
import itertools
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from . import similarity_index
from .matrix import ComparisonMatrix
from .models import ASTModel, CosineModel, JaccardModel, WinnowingModel
from .models.ai_detector import AIAssessment, AIDetector
from .websearch import WebSearchError, WebSearchProvider, extract_queries

#: Similarity modes eligible for web-source comparison. AI modes never search
#: the web — they assess a single document's own writing/coding style.
WEB_ELIGIBLE_MODES = {"code_similarity", "text_similarity"}

#: Web matches kept per uploaded file, sorted by score descending.
_MAX_WEB_MATCHES_PER_FILE = 5

#: Composition weights per similarity mode. Both modes blend two of the four
#: documented algorithms rather than picking one, mirroring how a real
#: plagiarism check triangulates evidence:
#:  - code_similarity: AST is the only rename-invariant signal, so it
#:    dominates (0.70) whenever both files are Python; winnowing (0.30)
#:    catches copy-paste-with-edits. Non-Python code (Java/C/C++) has no AST
#:    model, so it falls back to winnowing alone.
#:  - text_similarity: TF-IDF cosine (0.50) catches vocabulary-level
#:    similarity, winnowing (0.50) catches contiguous copied passages even
#:    after light paraphrasing — neither alone is sufficient.
_CODE_AST_WEIGHT = 0.70
_CODE_WINNOWING_WEIGHT = 0.30
_TEXT_COSINE_WEIGHT = 0.50
_TEXT_WINNOWING_WEIGHT = 0.50

#: Algorithms selectable per similarity mode, in UI display order. "auto" is
#: the mode's designed blend (see weights above); the rest force a single
#: named model, for demoing/reviewing each one individually. AST needs raw
#: Python source (`data["raw"]`, not `data["tokens"]`) and always scores 0.0
#: on non-Python input — callers should disable that choice for non-Python
#: pairs rather than surface a misleading zero.
ALGORITHMS_BY_MODE: dict[str, list[str]] = {
    "code_similarity": ["auto", "ast", "winnowing", "jaccard"],
    "text_similarity": ["auto", "cosine", "winnowing", "jaccard"],
    "ai_code": [],
    "ai_text": [],
}


@dataclass
class WebMatch:
    """One fetched web page compared against an uploaded file.

    `score` is the same blended (or forced) algorithm score `_compute_pair`
    computes for an uploaded-vs-uploaded pair, just run against the fetched
    page's text instead.
    """

    query: str
    url: str
    title: str
    score: float

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation of this match."""
        return {
            "query": self.query,
            "url": self.url,
            "title": self.title,
            "score": round(self.score, 4),
        }


@dataclass
class ScanResult:
    """Unified result of one `ScanEngine.compute()` call.

    Similarity modes (`code_similarity`, `text_similarity`) populate
    `matrix`, `similarity_indices`, and `source_breakdowns`. AI modes
    (`ai_code`, `ai_text`) populate `ai_assessments`. The unused half stays
    at its default rather than forcing `isinstance` checks at every call
    site — check `is_ai` instead. `web_matches` and `warnings` are only ever
    populated when `compute()` is given a `web_client`.
    """

    mode: str
    names: list[str]
    algorithm: str = "auto"
    matrix: ComparisonMatrix | None = None
    similarity_indices: dict[str, float] = field(default_factory=dict)
    source_breakdowns: dict[str, list[dict]] = field(default_factory=dict)
    ai_assessments: dict[str, AIAssessment] = field(default_factory=dict)
    web_matches: dict[str, list[WebMatch]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_ai(self) -> bool:
        """Whether this result came from an ai_code/ai_text scan."""
        return self.mode in ("ai_code", "ai_text")


class ScanEngine:
    """Orchestrates similarity and AI scans over a batch of files."""

    def __init__(self, mode: str = "text_similarity", algorithm: str = "auto"):
        """Select which mode to run, and optionally force a single algorithm.

        `algorithm="auto"` (default) runs the mode's designed blend. Any
        other value (`ast`, `cosine`, `winnowing`, `jaccard`) forces that one
        model instead, for `code_similarity`/`text_similarity` only — AI
        modes ignore `algorithm` entirely.
        """
        self.mode = mode.lower()
        self.algorithm = algorithm.lower()
        self.models = {
            "cosine": CosineModel(),
            "winnowing": WinnowingModel(),
            "jaccard": JaccardModel(),
            "ast": ASTModel(),
            "ai": AIDetector(),
        }

    def compute(
        self,
        file_data: dict,
        preprocessor=None,
        min_match_words: int = similarity_index.DEFAULT_MIN_MATCH_WORDS,
        web_client: WebSearchProvider | None = None,
        max_web_queries: int = 5,
        on_query: Callable[[str, int], None] | None = None,
        web_budget_seconds: float | None = None,
    ) -> ScanResult:
        """Run the scan and return a `ScanResult`.

        `preprocessor` is optional for similarity modes; when supplied, the
        per-document Similarity Index and ranked source breakdown are also
        computed (they need the stemmer/stopword set to find matched spans).

        `web_client`, when supplied alongside `preprocessor`, additionally
        compares every uploaded file against fetched web pages (see
        `_compute_web_matches`). Requires `preprocessor` — search results
        need tokenizing before they're comparable, so a `web_client` given
        without a `preprocessor` is a no-op with a warning attached rather
        than an error, since dropping the web comparison shouldn't fail an
        otherwise-normal similarity scan. `on_query`, if given, is called
        once per outbound search query as `on_query(query, result_count)` —
        callers use it to audit-log every request sent to a third party.
        """
        names = list(file_data.keys())
        result = ScanResult(mode=self.mode, names=names, algorithm=self.algorithm)

        if self.mode in ("ai_code", "ai_text"):
            detector = self.models["ai"]
            for name in names:
                data = file_data[name]
                if self.mode == "ai_code":
                    result.ai_assessments[name] = detector.assess_code(
                        data["raw"], data.get("language", "python")
                    )
                else:
                    result.ai_assessments[name] = detector.assess_text(data["raw"])
            return result

        matrix = ComparisonMatrix(names)
        for name_a, name_b in itertools.combinations(names, 2):
            data_a, data_b = file_data[name_a], file_data[name_b]
            score = self._compute_pair(data_a, data_b)
            matrix.set(names.index(name_a), names.index(name_b), score)
        result.matrix = matrix

        if preprocessor is not None:
            for name in names:
                result.similarity_indices[name] = similarity_index.similarity_index(
                    name, file_data, preprocessor, min_match_words
                )
                result.source_breakdowns[name] = similarity_index.source_breakdown(
                    name, file_data, preprocessor, min_match_words
                )

        if web_client is not None:
            if preprocessor is None:
                result.warnings.append(
                    "web_client was supplied without a preprocessor; web comparison skipped."
                )
            elif self.mode in WEB_ELIGIBLE_MODES:
                self._compute_web_matches(
                    result,
                    file_data,
                    preprocessor,
                    min_match_words,
                    web_client,
                    max_web_queries,
                    on_query,
                    web_budget_seconds,
                )

        return result

    def _compute_web_matches(
        self,
        result: ScanResult,
        file_data: dict,
        preprocessor,
        min_match_words: int,
        web_client: WebSearchProvider,
        max_web_queries: int,
        on_query: Callable[[str, int], None] | None = None,
        web_budget_seconds: float | None = None,
    ) -> None:
        """Populate `result.web_matches` and merge web sources into each
        file's Similarity Index / source breakdown.

        Web pages are merged into the dict passed to `similarity_index()`
        and `source_breakdown()` on a *per-file* basis — never into the
        shared `file_data` used for the uploaded-vs-uploaded matrix — so
        file A's web results never leak into file B's coverage numbers.
        Fetched pages are cached by URL across the whole call so two queries
        (or two files) returning the same page only fetch it once.

        `web_budget_seconds`, if given, caps the total wall-clock time spent
        searching/fetching across the whole call — checked between queries,
        not trusted to the caller, so one slow scan can't hang indefinitely.
        Once exceeded, remaining files/queries are skipped and a warning is
        attached; work already done is kept.
        """
        page_cache: dict[str, dict] = {}
        deadline = (
            time.monotonic() + web_budget_seconds if web_budget_seconds is not None else None
        )

        for name in result.names:
            if deadline is not None and time.monotonic() > deadline:
                result.warnings.append(
                    "Web search time budget exceeded; remaining files were skipped."
                )
                break

            data = file_data[name]
            language = data.get("language", "text")
            queries = extract_queries(data["raw"], language, max_web_queries)

            web_file_data: dict[str, dict] = {}
            matches: list[WebMatch] = []
            try:
                for query in queries:
                    if deadline is not None and time.monotonic() > deadline:
                        result.warnings.append(
                            f"Web search time budget exceeded while processing {name!r}."
                        )
                        break
                    hits = web_client.search(query, max_results=max_web_queries)
                    if on_query is not None:
                        on_query(query, len(hits))
                    for hit in hits:
                        if hit.url not in page_cache:
                            try:
                                page_text = web_client.fetch_page_text(hit.url)
                            except WebSearchError:
                                continue
                            tokens, kgrams = preprocessor.process(page_text, language="text")
                            page_cache[hit.url] = {
                                "raw": page_text,
                                "tokens": tokens,
                                "kgrams": kgrams,
                                "language": "text",
                            }
                        web_page = page_cache[hit.url]
                        web_file_data[hit.url] = web_page
                        score = self._compute_pair(data, web_page)
                        matches.append(WebMatch(query=query, url=hit.url, title=hit.title, score=score))
            except WebSearchError as e:
                result.warnings.append(f"Web search failed for {name!r}: {e}")

            matches.sort(key=lambda m: m.score, reverse=True)
            result.web_matches[name] = matches[:_MAX_WEB_MATCHES_PER_FILE]

            if web_file_data:
                merged = {**file_data, **web_file_data}
                result.similarity_indices[name] = similarity_index.similarity_index(
                    name, merged, preprocessor, min_match_words
                )
                result.source_breakdowns[name] = similarity_index.source_breakdown(
                    name, merged, preprocessor, min_match_words
                )

    def _compute_pair(self, data_a: dict, data_b: dict) -> float:
        if self.algorithm == "ast":
            return self.models["ast"].compute([data_a["raw"]], [data_b["raw"]])
        if self.algorithm in ("cosine", "winnowing", "jaccard"):
            return self.models[self.algorithm].compute(data_a["tokens"], data_b["tokens"])

        # algorithm == "auto": the mode's designed blend.
        if self.mode == "code_similarity":
            if data_a.get("language") == "python" and data_b.get("language") == "python":
                ast_score = self.models["ast"].compute([data_a["raw"]], [data_b["raw"]])
                win_score = self.models["winnowing"].compute(data_a["tokens"], data_b["tokens"])
                return (ast_score * _CODE_AST_WEIGHT) + (win_score * _CODE_WINNOWING_WEIGHT)
            # Non-Python code (Java/C/C++): no AST model, winnowing alone.
            return self.models["winnowing"].compute(data_a["tokens"], data_b["tokens"])

        if self.mode == "text_similarity":
            cos_score = self.models["cosine"].compute(data_a["tokens"], data_b["tokens"])
            win_score = self.models["winnowing"].compute(data_a["tokens"], data_b["tokens"])
            return (cos_score * _TEXT_COSINE_WEIGHT) + (win_score * _TEXT_WINNOWING_WEIGHT)

        # Fallback for an unrecognized mode.
        return self.models["jaccard"].compute(data_a["tokens"], data_b["tokens"])
