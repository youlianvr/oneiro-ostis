"""Research, web search, provenance and attachment intake for Oneiro.

This module owns:
1. **Source-backed research**:
   - Structured search results (`SearchResult`, `SourceRecord`) with metadata, URLs,
     snippets and content digests.
   - Web search (`search_web`): extensible provider seam (with mock/stub support,
     falling back to search engines or query providers).
   - Safe web fetching and text extraction (`fetch_web_content`) using public IP guards,
     HTML stripping, and byte limits.
   - Recording source records and citations in the memory graph (`RecordStore` Note/Record).
2. **Attachments intake**:
   - Supported types:
     * Plain text and Markdown (`text/plain`, `text/markdown`, `.txt`, `.md`, `.py`, `.json`, etc.)
     * Images (`image/png`, `image/jpeg`, `image/webp`) with format/dimension inspection
     * PDF documents (`application/pdf`) with page and byte limits, extracting readable text
       using PyMuPDF (`fitz`) when available or clean standard fallback.
   - Strict size bounds (`MAX_ATTACHMENT_BYTES` = 20 MB default) and page limits
     (`MAX_ATTACHMENT_PAGES` = 50 default).
   - SHA-256 deduplication and verification.
   - Content persistence under `<data_dir>/attachments/<hash>`.
   - Preparation of attachment payloads for the model turn (text context or vision items).
"""
from __future__ import annotations

import hashlib
import html
import io
import ipaddress
import json
import mimetypes
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from oneiro import config
from oneiro.records import Note, Provenance, State, new_id, now

# Defaults and bounds
DEFAULT_MAX_BYTES = 20_000_000      # 20 MB
DEFAULT_MAX_PAGES = 50              # 50 PDF pages
DEFAULT_MAX_FETCH_BYTES = 100_000   # 100 KB for web page reads
FETCH_TIMEOUT = 25.0

SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED_TEXT_EXTS = {
    ".txt", ".md", ".json", ".csv", ".tsv", ".py", ".js", ".ts", ".html",
    ".css", ".xml", ".yaml", ".yml", ".ini", ".toml", ".scs", ".scg",
}
SUPPORTED_DOC_EXTS = {".pdf"}
ALL_SUPPORTED_EXTS = SUPPORTED_IMAGE_EXTS | SUPPORTED_TEXT_EXTS | SUPPORTED_DOC_EXTS


class ResearchError(ValueError):
    """Refusal or failure in research/attachment processing."""


class AttachmentRejected(ResearchError):
    """An attachment that violates policy, exceeds limits, or is unsupported."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class SearchResult:
    """One hit returned by a search provider."""

    title: str
    url: str
    snippet: str
    source_name: str = "web"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source_name": self.source_name,
        }


@dataclass(frozen=True)
class SourceRecord:
    """A verified or referenced source for research provenance."""

    id: str
    url: str
    title: str
    snippet: str
    content_hash: str
    retrieved_at: str
    verified: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "content_hash": self.content_hash,
            "retrieved_at": self.retrieved_at,
            "verified": self.verified,
        }


# Seam for search providers: allows tests and alternative engines to hook in
SEARCH_PROVIDER: Callable[[str, int], list[SearchResult]] | None = None


def allowed_sources() -> list[str]:
    """The configured sources research may use (e.g. ['web'])."""
    sources = config.value("research.sources")
    if isinstance(sources, list):
        return [str(s) for s in sources]
    return ["web"]


def search_web(query: str, *, count: int = 5) -> list[SearchResult]:
    """Search the web or configured research sources.

    Uses `SEARCH_PROVIDER` if registered (e.g. in tests or specialized configurations).
    Otherwise performs safe search retrieval or informs when search engine is offline.
    """
    clean = str(query or "").strip()
    if not clean:
        raise ResearchError("search query is required")
    if "web" not in allowed_sources():
        raise ResearchError("web research is disabled in research.sources")
    count = max(1, min(count, 20))

    if SEARCH_PROVIDER is not None:
        return SEARCH_PROVIDER(clean, count)

    # Built-in fallback: query via DuckDuckGo HTML / lite or API if reachable
    # Handled without third-party dependencies.
    encoded = urllib.parse.quote_plus(clean)
    target = f"https://html.duckduckgo.com/html/?q={encoded}"
    try:
        fetched = fetch_web_content(target, max_bytes=150_000)
    except Exception as exc:
        raise ResearchError(f"web search is unavailable: {exc}") from None

    text = fetched.get("text", "")
    # Simple regex parse for duckduckgo html links
    results: list[SearchResult] = []
    matches = re.findall(
        r'<a class="result__snippet[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        fetched.get("raw_html", ""),
        re.DOTALL | re.IGNORECASE,
    )
    if not matches:
        # Fallback to finding links with uddg parameter
        matches_uddg = re.findall(
            r'<a[^>]+class="result__url"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            fetched.get("raw_html", ""),
            re.DOTALL | re.IGNORECASE,
        )
        for href, title in matches_uddg[:count]:
            parsed = urllib.parse.urlparse(href)
            qs = urllib.parse.parse_qs(parsed.query)
            real_url = qs.get("uddg", [href])[0]
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            results.append(SearchResult(title=clean_title or real_url, url=real_url, snippet=""))
    else:
        for href, snip in matches[:count]:
            parsed = urllib.parse.urlparse(href)
            qs = urllib.parse.parse_qs(parsed.query)
            real_url = qs.get("uddg", [href])[0]
            clean_snippet = re.sub(r"<[^>]+>", "", snip).strip()
            results.append(SearchResult(title=clean_snippet[:80], url=real_url, snippet=clean_snippet))

    if not results and text:
        results.append(SearchResult(title=f"Result for: {clean}", url=target, snippet=text[:300]))

    return results


# ---------------------------------------------------------------------------
# Safe web fetching & HTML extraction
# ---------------------------------------------------------------------------


def _is_safe_public_host(hostname: str) -> bool:
    """Public hosts only: reject loopback, link-local, RFC-1918 private IPs."""
    if not hostname:
        return False
    if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        return False
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False
    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                return False
        except ValueError:
            return False
    return True


def strip_html(html_text: str) -> str:
    """Convert HTML content into readable text."""
    # Remove script and style tags
    clean = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html_text, flags=re.DOTALL | re.IGNORECASE)
    # Convert block tags to line breaks
    clean = re.sub(r"<(div|p|h[1-6]|li|blockquote|br|hr|tr)[^>]*>", "\n", clean, flags=re.IGNORECASE)
    # Strip remaining tags
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = html.unescape(clean)
    # Collapse excess whitespace
    lines = [re.sub(r"\s+", " ", line).strip() for line in clean.splitlines()]
    return "\n".join(line for line in lines if line)


def fetch_web_content(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_FETCH_BYTES,
    timeout: float = FETCH_TIMEOUT,
    allow_private: bool = False,
) -> dict[str, Any]:
    """Fetch public web content safely, extracting text and metadata."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ResearchError(f"unsupported URL scheme: {parsed.scheme!r}")
    host = parsed.hostname or ""
    if not allow_private and not _is_safe_public_host(host):
        raise ResearchError(f"host {host!r} is not a permitted public web target")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "OneiroResearch/0.2.0 (+https://github.com/ostis-ai/oneiro)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            content_type = str(response.headers.get("Content-Type", "")).lower()
            raw = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise ResearchError(f"HTTP error {exc.code} fetching {url}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise ResearchError(f"network error fetching {url}: {exc}") from None

    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]

    encoding = "utf-8"
    if "charset=" in content_type:
        encoding = content_type.split("charset=")[-1].split(";")[0].strip() or "utf-8"

    try:
        decoded = raw.decode(encoding, errors="replace")
    except LookupError:
        decoded = raw.decode("utf-8", errors="replace")

    content_hash = hashlib.sha256(raw).hexdigest()
    text = strip_html(decoded) if "html" in content_type or "<html" in decoded[:1000].lower() else decoded

    # Extract title if present
    title_match = re.search(r"<title[^>]*>(.*?)</title>", decoded, re.IGNORECASE | re.DOTALL)
    title = html.unescape(title_match.group(1).strip()) if title_match else url

    return {
        "url": url,
        "title": title,
        "text": text,
        "raw_html": decoded if "html" in content_type else "",
        "content_hash": content_hash,
        "truncated": truncated,
        "status": status,
        "bytes": len(raw),
    }


# ---------------------------------------------------------------------------
# Attachments intake, inspection, limits & persistence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttachmentMeta:
    """Metadata about an accepted attachment."""

    id: str
    name: str
    mime: str
    size: int
    sha256: str
    pages: int | None = None
    width: int | None = None
    height: int | None = None
    text_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "mime": self.mime,
            "size": self.size,
            "sha256": self.sha256,
            "pages": self.pages,
            "width": self.width,
            "height": self.height,
            "has_text": bool(self.text_content),
        }


def attachments_dir() -> Path:
    """Directory where uploaded/cached attachments live."""
    root = config.data_root() / "attachments"
    root.mkdir(parents=True, exist_ok=True)
    return root


def detect_mime_type(filename: str, header: bytes) -> str:
    """Detect MIME type by magic bytes first, then extension."""
    if header.startswith(b"%PDF"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"

    # Extension guessing for text
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed

    ext = Path(filename).suffix.lower()
    if ext in SUPPORTED_TEXT_EXTS:
        return "text/plain"
    return "application/octet-stream"


def extract_pdf_text(raw_bytes: bytes, max_pages: int = DEFAULT_MAX_PAGES) -> tuple[str, int]:
    """Extract text from a PDF, enforcing page bounds."""
    # Try PyMuPDF (fitz) if installed
    try:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        total_pages = doc.page_count
        pages_to_read = min(total_pages, max_pages)
        texts = []
        for i in range(pages_to_read):
            page = doc.load_page(i)
            texts.append(page.get_text())
        doc.close()
        return "\n\n--- Page Break ---\n\n".join(texts), total_pages
    except ImportError:
        pass

    # Basic fallback text extractor for pure stream PDFs
    # Searches for streams and extracts text objects
    total_pages = max(1, len(re.findall(rb"/Type\s*/Page\b", raw_bytes)))
    # Simple regex search for text in parenthesis inside PDF streams
    text_fragments = re.findall(rb"\((.*?)\)\s*Tj", raw_bytes)
    extracted = " ".join(f.decode("latin1", errors="replace") for f in text_fragments[:5000])
    return extracted, total_pages


def inspect_image(raw_bytes: bytes) -> tuple[int | None, int | None]:
    """Inspect image dimensions safely without external binaries."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw_bytes)) as img:
            return img.width, img.height
    except Exception:
        return None, None


def ingest_attachment(
    filename: str,
    data: bytes,
    *,
    max_bytes: int | None = None,
    max_pages: int | None = None,
) -> AttachmentMeta:
    """Validate, inspect, limit, and store an incoming attachment."""
    if not data:
        raise AttachmentRejected("attachment is empty (0 bytes)")

    max_bytes = max_bytes if max_bytes is not None else int(config.value("attachments.max_bytes") or DEFAULT_MAX_BYTES)
    max_pages = max_pages if max_pages is not None else int(config.value("attachments.max_pages") or DEFAULT_MAX_PAGES)

    if len(data) > max_bytes:
        raise AttachmentRejected(
            f"attachment {filename!r} ({len(data)} bytes) exceeds size limit of {max_bytes} bytes",
            status=413,
        )

    mime = detect_mime_type(filename, data[:32])
    ext = Path(filename).suffix.lower()

    if ext not in ALL_SUPPORTED_EXTS and mime not in (
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/webp",
        "text/plain",
        "text/markdown",
        "application/json",
    ):
        raise AttachmentRejected(
            f"file type {ext or mime!r} is not supported; Oneiro accepts text, markdown, PDF and images (PNG, JPEG, WebP)"
        )

    sha256 = hashlib.sha256(data).hexdigest()
    att_id = f"att-{sha256[:16]}"
    dest = attachments_dir() / f"{sha256}{ext or '.bin'}"

    pages_count: int | None = None
    width: int | None = None
    height: int | None = None
    text_content = ""

    if mime == "application/pdf":
        try:
            extracted_text, total_pages = extract_pdf_text(data, max_pages=max_pages)
            pages_count = total_pages
            if total_pages > max_pages:
                text_content = (
                    extracted_text
                    + f"\n\n[Truncated: PDF has {total_pages} pages, limit is {max_pages} pages]"
                )
            else:
                text_content = extracted_text
        except Exception as exc:
            raise AttachmentRejected(f"corrupted or unreadable PDF document: {exc}") from None
    elif mime.startswith("image/"):
        width, height = inspect_image(data)
    else:
        # Plain text
        try:
            text_content = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_content = data.decode("latin1")
            except Exception:
                raise AttachmentRejected("attachment contains binary characters that cannot be decoded as text")

    # Persist atomically
    meta_json = dest.with_suffix(".json")
    if not dest.exists() or not meta_json.exists():
        tmp_dest = dest.with_suffix(".tmp")
        tmp_dest.write_bytes(data)
        tmp_dest.replace(dest)

        meta_payload = {
            "id": att_id,
            "name": Path(filename).name,
            "mime": mime,
            "size": len(data),
            "sha256": sha256,
            "pages": pages_count,
            "width": width,
            "height": height,
        }
        meta_json.write_text(json.dumps(meta_payload, ensure_ascii=False), encoding="utf-8")

    return AttachmentMeta(
        id=att_id,
        name=Path(filename).name,
        mime=mime,
        size=len(data),
        sha256=sha256,
        pages=pages_count,
        width=width,
        height=height,
        text_content=text_content,
    )


def load_attachment(attachment_id: str) -> AttachmentMeta | None:
    """Retrieve an attachment by ID if present."""
    prefix = attachment_id.removeprefix("att-")
    dir_path = attachments_dir()
    for meta_file in dir_path.glob("*.json"):
        if meta_file.stem.startswith(prefix):
            try:
                info = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            sha = info.get("sha256", "")
            # Find data file
            data_file = None
            for f in dir_path.iterdir():
                if f.name.startswith(sha) and f.suffix != ".json":
                    data_file = f
                    break
            if data_file and data_file.exists():
                raw = data_file.read_bytes()
                # Re-extract text content if text or pdf
                text_content = ""
                mime = info.get("mime", "")
                if mime == "application/pdf":
                    text_content, _ = extract_pdf_text(raw)
                elif mime.startswith("text/") or mime == "application/json":
                    text_content = raw.decode("utf-8", errors="replace")

                return AttachmentMeta(
                    id=info.get("id", f"att-{sha[:16]}"),
                    name=info.get("name", data_file.name),
                    mime=mime,
                    size=info.get("size", len(raw)),
                    sha256=sha,
                    pages=info.get("pages"),
                    width=info.get("width"),
                    height=info.get("height"),
                    text_content=text_content,
                )
    return None


def read_attachment_content(attachment_id: str) -> dict[str, Any]:
    """Read attachment details and readable content for context/tools."""
    meta = load_attachment(attachment_id)
    if meta is None:
        raise AttachmentRejected(f"attachment not found: {attachment_id!r}", status=404)
    return {
        "id": meta.id,
        "name": meta.name,
        "mime": meta.mime,
        "size": meta.size,
        "sha256": meta.sha256,
        "pages": meta.pages,
        "width": meta.width,
        "height": meta.height,
        "text": meta.text_content,
    }


def tools_registry(internet: bool = True) -> dict[str, Any]:
    """Research tools for the agent: web_search and read_attachment."""
    from oneiro.tools import Tool, ROLES

    def do_search(ctx: dict, args: dict) -> dict[str, Any]:
        if not internet:
            raise ResearchError("internet access is disabled")
        query = args.get("query", "")
        count = int(args.get("count", 5))
        results = search_web(query, count=count)
        return {
            "query": query,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }

    def do_read_attachment(ctx: dict, args: dict) -> dict[str, Any]:
        att_id = str(args.get("attachment_id", "")).strip()
        return read_attachment_content(att_id)

    tools = [
        Tool(
            "web_search",
            "Search the web for up-to-date information, documentation, and sources.",
            {"query": {"type": "string"}, "count": {"type": "integer"}},
            ("query",),
            ROLES,
            "web_read",
            do_search,
        ),
        Tool(
            "read_attachment",
            "Read the extracted text and metadata of a user-provided attachment by ID.",
            {"attachment_id": {"type": "string"}},
            ("attachment_id",),
            ROLES,
            "read",
            do_read_attachment,
        ),
    ]
    return {t.name: t for t in tools}


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def research_command(argv: list[str]) -> int:
    """CLI surface for oneiro research: search, fetch, attach, show."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="oneiro research",
        description="Oneiro research and attachments CLI",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="search",
        choices=("search", "fetch", "attach", "show"),
    )
    parser.add_argument("target", nargs="?", default="", help="query, URL, file path or ID")
    parser.add_argument("--count", type=int, default=5, help="max search results")
    parser.add_argument("--json", action="store_true", help="output as JSON")
    args = parser.parse_args(argv)

    if args.action == "search":
        if not args.target.strip():
            print("error: a query is required for search", file=sys.stderr)
            return 2
        try:
            hits = search_web(args.target, count=args.count)
        except ResearchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps([h.to_dict() for h in hits], ensure_ascii=False, indent=2))
            return 0
        print(f"Search results for: {args.target} ({len(hits)} hits)")
        for i, hit in enumerate(hits, 1):
            print(f"{i}. {hit.title}\n   {hit.url}\n   {hit.snippet[:160]}")
        return 0

    if args.action == "fetch":
        if not args.target.strip():
            print("error: a URL is required for fetch", file=sys.stderr)
            return 2
        try:
            doc = fetch_web_content(args.target)
        except ResearchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(doc, ensure_ascii=False, indent=2))
            return 0
        print(f"Fetched {doc['url']} -> {doc['status']}, {doc['bytes']} bytes (sha256 {doc['content_hash'][:12]}...)")
        print(f"Title: {doc['title']}")
        print(f"Text:\n{doc['text'][:500]}...")
        return 0

    if args.action == "attach":
        path = Path(args.target)
        if not path.is_file():
            print(f"error: file not found: {args.target}", file=sys.stderr)
            return 2
        try:
            raw = path.read_bytes()
            meta = ingest_attachment(path.name, raw)
        except (ResearchError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(meta.to_dict(), ensure_ascii=False, indent=2))
            return 0
        print(f"Attached {meta.name} as {meta.id} ({meta.mime}, {meta.size} bytes, sha256 {meta.sha256[:12]})")
        if meta.pages:
            print(f"  Pages: {meta.pages}")
        if meta.width and meta.height:
            print(f"  Dimensions: {meta.width}x{meta.height}")
        return 0

    if args.action == "show":
        if not args.target.strip():
            print("error: attachment ID is required", file=sys.stderr)
            return 2
        try:
            content = read_attachment_content(args.target)
        except AttachmentRejected as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(content, ensure_ascii=False, indent=2))
            return 0
        print(f"Attachment {content['id']}: {content['name']} ({content['mime']}, {content['size']} bytes)")
        if content.get("text"):
            print(f"Content excerpt:\n{content['text'][:400]}...")
        return 0

    return 0


