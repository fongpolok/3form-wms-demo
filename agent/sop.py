"""
Company SOP library (the RAG section): the PIC uploads SOPs (PDF, Word, Markdown,
text). Text is extracted, split into passages and added to keyword search, so the
agent can quote them. Originals are kept under media/sop/. Starts empty.
"""
import io
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from accounts import audit
from core import config, mongo

from . import search

logger = logging.getLogger("agent")
ALLOWED = {".pdf", ".docx", ".md", ".txt"}


class SopError(Exception):
    pass


def extract_text(filename, data):
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages), len(reader.pages)
    if ext == ".docx":
        import docx
        d = docx.Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in d.paragraphs if p.text.strip()), None
    return data.decode("utf-8", errors="replace"), None


def chunk(text, size=None):
    size = size or int(config.get("search.sop_chunk_chars", 900))
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        while len(p) > size:                  # very long paragraph: hard split
            out.append(p[:size]); p = p[size:]
        if len(cur) + len(p) + 2 > size and cur:
            out.append(cur); cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out


def upload(account, uploaded_file, title=""):
    name = uploaded_file.name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise SopError("Upload a PDF, Word (.docx), Markdown (.md) or text (.txt) file.")
    max_mb = float(config.get("search.sop_max_upload_mb", 20))
    if uploaded_file.size > max_mb * 1024 * 1024:
        raise SopError(f"File is larger than {max_mb:g} MB.")
    data = uploaded_file.read()
    try:
        text, pages = extract_text(name, data)
    except Exception as exc:  # noqa: BLE001 - damaged files give a plain message
        logger.warning("SOP text extraction failed for %s: %s", name, exc)
        raise SopError("Could not read text from this file. Is it a scanned image or damaged?")
    if not text.strip():
        raise SopError("No text found in this file (a scanned PDF needs OCR first).")
    sop_id = f"SOP-{uuid.uuid4().hex[:8].upper()}"
    folder = Path(settings.MEDIA_ROOT) / "sop" / account.tenant_openid[:8]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{sop_id}{ext}").write_bytes(data)
    parts = chunk(text)
    now = datetime.now(timezone.utc)
    title = title.strip() or Path(name).stem
    search.upsert([{"doc_id": f"sop:{sop_id}:{i}", "tenant_openid": account.tenant_openid, "kind": "sop",
                    "title": f"{title} (part {i + 1})", "text": p, "ref": sop_id, "ts": now} for i, p in enumerate(parts)])
    doc = {"sop_id": sop_id, "tenant_openid": account.tenant_openid, "title": title, "filename": name,
           "size": len(data), "pages": pages, "chunks": len(parts), "chars": len(text),
           "uploaded_by": account.display_name, "uploaded_at": now}
    mongo.db().sop_documents.insert_one(dict(doc))
    audit.record(account, "sop.upload", "sop", sop_id, after={"title": title, "filename": name, "chunks": len(parts)})
    logger.info("SOP %s uploaded: %s, %d passages", sop_id, name, len(parts))
    return doc


def remove(account, sop_id):
    db = mongo.db()
    doc = db.sop_documents.find_one({"sop_id": sop_id, "tenant_openid": account.tenant_openid})
    if not doc:
        raise SopError("SOP not found.")
    db.sop_documents.delete_one({"sop_id": sop_id})
    search.coll().delete_many({"ref": sop_id, "kind": "sop"})
    audit.record(account, "sop.remove", "sop", sop_id, before={"title": doc["title"]})
    return True


def list_docs(tenant):
    return list(mongo.db().sop_documents.find({"tenant_openid": tenant}, {"_id": 0}).sort("uploaded_at", -1))
