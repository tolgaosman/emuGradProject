""" websearch.py — the only module that talks to a search API or fetches arbitrary web pages.

Mirrors how `web/src/api/client.ts` is "the only place that talks HTTP" on
the frontend: nothing else in this codebase should import `requests` or know
about the Google Programmable Search endpoint shape. Everything here is a
deliberate, contained exception to the project's "must work fully offline"
rule (see CLAUDE.md) — gated behind config that must be explicitly
provisioned (`WEB_SEARCH_API_KEY` / `WEB_SEARCH_ENGINE_ID`), never on by
accident.
"""

import os
from dataclasses import dataclass
from typing import Protocol

import requests
from bs4 import BeautifulSoup
from nltk.tokenize import sent_tokenize

from .language import CODE_LANGUAGES, strip_comments_and_strings

_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

#: Response Content-Types treated as fetchable HTML. Anything else (images,
#: PDFs picked up by search, octet-streams, ...) is rejected before download.
_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

#: Elements whose text carries no page content (nav chrome, scripts, styles).
_STRIP_TAGS = ("script", "style", "nav", "footer", "header", "aside")


class WebSearchProvider(Protocol):
    """Structural interface `ScanEngine` depends on, instead of the concrete `WebSearchClient`.

    Lets tests inject a fake without subclassing the real client.
    """

    def search(self, query: str, max_results: int = 5) -> list["SearchResult"]:
        """Run one search query and return its organic results."""
        ...

    def fetch_page_text(self, url: str, max_bytes: int = 2_000_000) -> str:
        """Fetch `url` and return its visible text."""
        ...


class WebSearchError(Exception):
    """Raised for any search-provider or page-fetch failure.

    Callers (the engine) decide whether to degrade a single file's web
    matches to empty or let the error propagate — this module never decides
    that on their behalf.
    """


@dataclass
class SearchResult:
    """One organic result from a search query."""

    url: str
    title: str
    snippet: str


class WebSearchClient:
    """Thin client for Google's Custom Search JSON API plus a page fetcher.

    Reads its credentials from the environment by default, mirroring
    `ScanRepository`'s DB-config pattern in `repository.py`.
    """

    def __init__(
        self,
        api_key: str | None = None,
        engine_id: str | None = None,
        timeout: float | None = None,
    ):
        """Read credentials/timeout from the environment when not given explicitly."""
        self.api_key = api_key or os.environ.get("WEB_SEARCH_API_KEY", "")
        self.engine_id = engine_id or os.environ.get("WEB_SEARCH_ENGINE_ID", "")
        self.timeout = timeout or float(os.environ.get("WEB_SEARCH_TIMEOUT_SECONDS", "8"))

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Run one search query. Raises `WebSearchError` on any failure.

        Does not retry — a scan should fail fast on a bad key or a down
        provider, not hang.
        """
        try:
            resp = requests.get(
                _SEARCH_URL,
                params={
                    "key": self.api_key,
                    "cx": self.engine_id,
                    "q": query,
                    "num": max(1, min(max_results, 10)),
                },
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise WebSearchError(f"Search request failed: {e}") from e

        if resp.status_code != 200:
            raise WebSearchError(
                f"Search API returned {resp.status_code} for query {query!r}: {resp.text[:200]}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise WebSearchError(f"Search API returned non-JSON response: {e}") from e

        items = payload.get("items", [])
        return [
            SearchResult(
                url=item.get("link", ""),
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
            )
            for item in items
            if item.get("link")
        ][:max_results]

    def fetch_page_text(self, url: str, max_bytes: int = 2_000_000) -> str:
        """Fetch `url` and return its visible text, or raise `WebSearchError`.

        Streams the response so a hostile/huge page can't exhaust memory or
        hang the request past `max_bytes`; rejects non-HTML content types
        before reading the body at all.
        """
        try:
            resp = requests.get(url, timeout=self.timeout, stream=True)
        except requests.RequestException as e:
            raise WebSearchError(f"Fetch failed for {url}: {e}") from e

        content_type = resp.headers.get("Content-Type", "").lower()
        if not any(ct in content_type for ct in _HTML_CONTENT_TYPES):
            resp.close()
            raise WebSearchError(f"Unsupported content type {content_type!r} for {url}")

        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in resp.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > max_bytes:
                    raise WebSearchError(f"Page at {url} exceeded {max_bytes} byte cap")
                chunks.append(chunk)
        finally:
            resp.close()

        html = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(_STRIP_TAGS):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)


def _rank_text_queries(raw_text: str, max_queries: int) -> list[str]:
    """Pick the longest, least stopword-heavy sentences as search queries."""
    try:
        sentences = sent_tokenize(raw_text)
    except LookupError:
        import nltk

        nltk.download("punkt")
        nltk.download("punkt_tab")
        sentences = sent_tokenize(raw_text)

    candidates = [s.strip() for s in sentences if len(s.split()) >= 6]
    candidates.sort(key=lambda s: len(s), reverse=True)
    return candidates[:max_queries]


def _rank_code_queries(raw_text: str, language: str, max_queries: int) -> list[str]:
    """Pick the most distinctive non-comment, non-blank lines as queries.

    Whole-line literal search finds copied code on GitHub/Stack Overflow far
    more reliably than a semantic query would — the goal is an exact or
    near-exact substring hit, not a paraphrase match.
    """
    stripped = strip_comments_and_strings(raw_text, language)
    lines = [ln.strip() for ln in stripped.splitlines()]
    candidates = [ln for ln in lines if len(ln) >= 12]
    # Rank by distinctive-identifier density: more unique alphabetic runs of
    # length >= 3 per character is a cheap proxy for "not boilerplate"
    # (closing braces, single-word lines, etc. rank low).
    candidates.sort(
        key=lambda ln: len(set(w.lower() for w in ln.split() if len(w) >= 3)) / max(1, len(ln)),
        reverse=True,
    )
    return candidates[:max_queries]


def extract_queries(raw_text: str, language: str, max_queries: int = 5) -> list[str]:
    """Turn a document into a handful of distinctive search phrases.

    Deterministic given the same input, which is what makes this testable
    without a live network call. Text documents rank sentences by length;
    code documents rank non-comment lines by identifier density.
    """
    if not raw_text.strip():
        return []
    if language in CODE_LANGUAGES:
        return _rank_code_queries(raw_text, language, max_queries)
    return _rank_text_queries(raw_text, max_queries)
