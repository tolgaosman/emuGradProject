""" test_websearch.py — WebSearchClient and extract_queries.

Nothing here makes a real network call: `requests.get` is monkeypatched in
every test that would otherwise reach the network, matching the project's
"test suite must never require [an external service]" rule extended from the
database to this new outbound dependency.
"""
import pytest
from src.websearch import (
    SearchResult,
    WebSearchClient,
    WebSearchError,
    extract_queries,
)


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None, chunks=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}
        self._chunks = chunks or []
        self.encoding = "utf-8"
        self.closed = False

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data

    def iter_content(self, chunk_size=65536):
        yield from self._chunks

    def close(self):
        self.closed = True


def test_search_returns_results_from_mocked_response(monkeypatch):
    payload = {
        "items": [
            {"link": "https://example.com/a", "title": "A", "snippet": "snippet a"},
            {"link": "https://example.com/b", "title": "B", "snippet": "snippet b"},
        ]
    }

    def fake_get(url, params=None, timeout=None):
        assert "customsearch" in url
        assert params["q"] == "hello world"
        return _FakeResponse(status_code=200, json_data=payload)

    monkeypatch.setattr("src.websearch.requests.get", fake_get)
    client = WebSearchClient(api_key="key", engine_id="cx")
    results = client.search("hello world")

    assert results == [
        SearchResult(url="https://example.com/a", title="A", snippet="snippet a"),
        SearchResult(url="https://example.com/b", title="B", snippet="snippet b"),
    ]


def test_search_skips_items_without_a_link(monkeypatch):
    payload = {"items": [{"title": "No link"}, {"link": "https://example.com/c", "title": "C"}]}
    monkeypatch.setattr(
        "src.websearch.requests.get", lambda *a, **k: _FakeResponse(200, json_data=payload)
    )
    client = WebSearchClient(api_key="key", engine_id="cx")
    results = client.search("q")
    assert len(results) == 1
    assert results[0].url == "https://example.com/c"


def test_search_raises_on_non_200(monkeypatch):
    monkeypatch.setattr(
        "src.websearch.requests.get", lambda *a, **k: _FakeResponse(403, text="quota exceeded")
    )
    client = WebSearchClient(api_key="key", engine_id="cx")
    with pytest.raises(WebSearchError, match="403"):
        client.search("q")


def test_search_raises_on_network_error(monkeypatch):
    import requests

    def raise_it(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr("src.websearch.requests.get", raise_it)
    client = WebSearchClient(api_key="key", engine_id="cx")
    with pytest.raises(WebSearchError, match="Search request failed"):
        client.search("q")


def test_search_raises_on_non_json_response(monkeypatch):
    monkeypatch.setattr(
        "src.websearch.requests.get", lambda *a, **k: _FakeResponse(200, json_data=None)
    )
    client = WebSearchClient(api_key="key", engine_id="cx")
    with pytest.raises(WebSearchError, match="non-JSON"):
        client.search("q")


def test_fetch_page_text_strips_chrome_and_returns_visible_text(monkeypatch):
    html = (
        b"<html><head><style>.x{}</style></head><body>"
        b"<nav>Home</nav><script>evil()</script>"
        b"<p>Real content here.</p><footer>Bye</footer></body></html>"
    )
    resp = _FakeResponse(
        200, headers={"Content-Type": "text/html; charset=utf-8"}, chunks=[html]
    )
    monkeypatch.setattr("src.websearch.requests.get", lambda *a, **k: resp)

    client = WebSearchClient(api_key="key", engine_id="cx")
    text = client.fetch_page_text("https://example.com/page")

    assert "Real content here." in text
    assert "evil()" not in text
    assert "Home" not in text
    assert "Bye" not in text
    assert resp.closed


def test_fetch_page_text_rejects_non_html_content_type(monkeypatch):
    resp = _FakeResponse(200, headers={"Content-Type": "application/pdf"})
    monkeypatch.setattr("src.websearch.requests.get", lambda *a, **k: resp)
    client = WebSearchClient(api_key="key", engine_id="cx")
    with pytest.raises(WebSearchError, match="Unsupported content type"):
        client.fetch_page_text("https://example.com/file.pdf")
    assert resp.closed


def test_fetch_page_text_enforces_byte_cap(monkeypatch):
    big_chunk = b"x" * 1000
    resp = _FakeResponse(
        200, headers={"Content-Type": "text/html"}, chunks=[big_chunk, big_chunk, big_chunk]
    )
    monkeypatch.setattr("src.websearch.requests.get", lambda *a, **k: resp)
    client = WebSearchClient(api_key="key", engine_id="cx")
    with pytest.raises(WebSearchError, match="byte cap"):
        client.fetch_page_text("https://example.com/huge", max_bytes=1500)
    assert resp.closed


def test_fetch_page_text_raises_on_network_error(monkeypatch):
    import requests

    def raise_it(*a, **k):
        raise requests.Timeout("slow")

    monkeypatch.setattr("src.websearch.requests.get", raise_it)
    client = WebSearchClient(api_key="key", engine_id="cx")
    with pytest.raises(WebSearchError, match="Fetch failed"):
        client.fetch_page_text("https://example.com/slow")


def test_extract_queries_empty_text_returns_empty_list():
    assert extract_queries("", "text") == []
    assert extract_queries("   ", "python") == []


def test_extract_queries_text_ranks_longer_sentences_first():
    text = (
        "Short one. "
        "This is a considerably longer sentence with many more words in it. "
        "Also short."
    )
    queries = extract_queries(text, "text", max_queries=2)
    assert len(queries) == 1  # only one sentence has >= 6 words
    assert "considerably longer sentence" in queries[0]


def test_extract_queries_is_deterministic():
    text = "One two three four five six seven. Another distinct sentence right here today."
    first = extract_queries(text, "text", max_queries=5)
    second = extract_queries(text, "text", max_queries=5)
    assert first == second


def test_extract_queries_code_strips_comments_and_short_lines():
    code = (
        "# a short comment\n"
        "def compute_average(values):\n"
        "    return sum(values) / len(values)\n"
        "\n"
        "x = 1\n"
    )
    queries = extract_queries(code, "python", max_queries=5)
    assert any("compute_average" in q for q in queries)
    assert not any(q.startswith("#") for q in queries)
    assert "x = 1" not in queries  # too short (< 12 chars) to be distinctive


def test_extract_queries_respects_max_queries():
    text = " ".join(f"sentence number {i} has exactly six words total." for i in range(10))
    queries = extract_queries(text, "text", max_queries=3)
    assert len(queries) <= 3
