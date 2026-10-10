"""Unit and adversarial tests for attachment intake, format inspection, bounds, and turns."""
from __future__ import annotations

import io
import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, Model, csrf_of, isolate, make_app, post
from oneiro import config, research
from oneiro.research import AttachmentRejected, ingest_attachment, load_attachment


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def test_empty_attachment_is_rejected():
    with pytest.raises(AttachmentRejected, match="attachment is empty"):
        ingest_attachment("empty.txt", b"")


def test_oversized_attachment_is_rejected():
    with pytest.raises(AttachmentRejected, match="exceeds size limit"):
        ingest_attachment("huge.txt", b"a" * 1000, max_bytes=500)


def test_unsupported_binary_format_is_rejected():
    # Executable header or unknown binary format
    with pytest.raises(AttachmentRejected, match="is not supported"):
        ingest_attachment("payload.exe", b"MZ\x90\x00\x03\x00\x00\x00")


def test_text_attachment_ingest_and_retrieval():
    content = "Hello, this is a research note about OSTIS semantic models."
    meta = ingest_attachment("notes.txt", content.encode("utf-8"))
    assert meta.name == "notes.txt"
    assert meta.mime == "text/plain"
    assert meta.size == len(content.encode("utf-8"))
    assert meta.text_content == content
    assert meta.sha256

    loaded = load_attachment(meta.id)
    assert loaded is not None
    assert loaded.id == meta.id
    assert loaded.text_content == content


def test_image_attachment_inspects_dimensions():
    try:
        from PIL import Image

        buf = io.BytesIO()
        img = Image.new("RGB", (120, 80), color="blue")
        img.save(buf, format="PNG")
        data = buf.getvalue()

        meta = ingest_attachment("screenshot.png", data)
        assert meta.mime == "image/png"
        assert meta.width == 120
        assert meta.height == 80
        assert meta.size == len(data)
    except ImportError:
        pytest.skip("PIL is not available")


def test_pdf_attachment_reading_and_page_limits():
    # Construct a minimal single-page PDF with text
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
        b"3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R>> endobj\n"
        b"4 0 obj <</Length 44>> stream\n"
        b"BT /F1 12 Tf 72 712 Td (OSTIS knowledge graph) Tj ET\n"
        b"endstream\n"
        b"endobj\n"
        b"xref\n0 5\n0000000000 65535 f \n"
        b"trailer <</Size 5 /Root 1 0 R>>\n"
        b"startxref\n250\n%%EOF"
    )
    meta = ingest_attachment("report.pdf", pdf_bytes, max_pages=10)
    assert meta.mime == "application/pdf"
    assert meta.pages is not None
    assert meta.pages >= 1


def test_corrupted_pdf_is_rejected_or_handled_safely():
    # Header says PDF but body is corrupt
    corrupt = b"%PDF-1.4 completely invalid stream data without catalog or xref %%EOF"
    # Either rejected or parsed safely without crash
    try:
        meta = ingest_attachment("corrupt.pdf", corrupt)
        assert meta.mime == "application/pdf"
    except AttachmentRejected as exc:
        assert "unreadable PDF" in str(exc) or "corrupted" in str(exc)


def test_message_with_attachment_only_is_accepted_in_http_api(tmp_path, monkeypatch):
    model = Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        token = csrf_of(client)

        # Upload attachment first with valid CSRF header
        upload_resp = client.post(
            "/api/attachments",
            headers={
                "X-Oneiro-CSRF": token,
                "X-Filename": "data.txt",
                "Content-Type": "application/octet-stream",
            },
            content=b"Sample context data for the model",
        )
        assert upload_resp.status_code == 200, upload_resp.text
        att_id = upload_resp.json()["id"]

        # Send message with empty text but with attachment
        msg_resp = post(
            client,
            "/api/message",
            {"text": "", "attachments": [att_id], "client_id": "client-att-0001"},
            token,
        )
        assert msg_resp.status_code == 200, msg_resp.text
        assert msg_resp.json()["reply"]["text"].startswith("answer:")
        # Model should have received the attachment content in its message context
        assert "Sample context data for the model" in model.messages[0][-1]["content"]


def test_attachment_download_endpoint(tmp_path, monkeypatch):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        token = csrf_of(client)
        upload_resp = client.post(
            "/api/attachments",
            headers={
                "X-Oneiro-CSRF": token,
                "X-Filename": "code.py",
                "Content-Type": "text/plain",
            },
            content=b"def test(): pass\n",
        )
        assert upload_resp.status_code == 200, upload_resp.text
        att_id = upload_resp.json()["id"]

        get_resp = client.get(f"/api/attachments/{att_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "code.py"
        assert "def test(): pass" in get_resp.json()["text"]
