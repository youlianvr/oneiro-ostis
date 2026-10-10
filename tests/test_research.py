"""Unit and adversarial tests for research and source-backed citations."""
from __future__ import annotations

import pytest

from oneiro import config, research
from oneiro.research import (
    AttachmentRejected,
    ResearchError,
    SearchResult,
    fetch_web_content,
    search_web,
    strip_html,
)


@pytest.fixture(autouse=True)
def isolate_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setenv("ONEIRO_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr(research, "SEARCH_PROVIDER", None)


def test_html_stripping_normalizes_text_cleanly():
    raw_html = """
    <html>
        <head><title>Test Title</title><script>var x = 1;</script></head>
        <body>
            <h1>Main Header</h1>
            <p>First paragraph with <b>bold</b> and &amp; entities.</p>
            <div>Second block of text.</div>
        </body>
    </html>
    """
    stripped = strip_html(raw_html)
    assert "Main Header" in stripped
    assert "First paragraph with bold and & entities." in stripped
    assert "Second block of text." in stripped
    assert "var x = 1;" not in stripped


def test_search_web_validates_query_and_bounds():
    with pytest.raises(ResearchError, match="search query is required"):
        search_web("")

    with pytest.raises(ResearchError, match="search query is required"):
        search_web("   ")


def test_search_web_uses_registered_provider(monkeypatch):
    def fake_provider(query: str, count: int) -> list[SearchResult]:
        return [
            SearchResult(title=f"Hit for {query}", url="https://example.com/test", snippet="Relevant snippet")
        ]

    monkeypatch.setattr(research, "SEARCH_PROVIDER", fake_provider)
    hits = search_web("ostis architecture", count=3)
    assert len(hits) == 1
    assert hits[0].title == "Hit for ostis architecture"
    assert hits[0].url == "https://example.com/test"
    assert hits[0].snippet == "Relevant snippet"


def test_search_web_refuses_when_disabled_in_sources(monkeypatch):
    config.save({"research.sources": ["local"]})
    with pytest.raises(ResearchError, match="web research is disabled"):
        search_web("query")


def test_fetch_web_content_blocks_private_and_loopback_hosts():
    for target in ("http://localhost/admin", "http://127.0.0.1:8000/", "http://192.168.1.1/router"):
        with pytest.raises(ResearchError, match="not a permitted public web target"):
            fetch_web_content(target)


def test_fetch_web_content_validates_schemes():
    for target in ("ftp://files.example.com", "file:///etc/passwd", "gopher://old.net"):
        with pytest.raises(ResearchError, match="unsupported URL scheme"):
            fetch_web_content(target)


def test_research_tools_registration_and_execution(monkeypatch):
    tools = research.tools_registry(internet=True)
    assert "web_search" in tools
    assert "read_attachment" in tools

    def stub_search(query: str, count: int) -> list[SearchResult]:
        return [SearchResult(title="Docs", url="https://proc.ostis.net", snippet="Semantic tools")]

    monkeypatch.setattr(research, "SEARCH_PROVIDER", stub_search)

    search_tool = tools["web_search"]
    out = search_tool.handler({}, {"query": "ostis", "count": 2})
    assert out["count"] == 1
    assert out["results"][0]["url"] == "https://proc.ostis.net"


def test_research_tool_refuses_when_internet_disabled():
    tools = research.tools_registry(internet=False)
    search_tool = tools["web_search"]
    with pytest.raises(ResearchError, match="internet access is disabled"):
        search_tool.handler({}, {"query": "anything"})
