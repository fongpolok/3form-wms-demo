"""
Keyword search (English + 中文) over one corpus collection `search_docs`:
scrap / downtime notes, work orders, agent advice, SOP chunks.

Indexes (MongoDB Atlas Search, created by `manage.py search_setup`):
  tf_text    full-text, lucene.standard + lucene.cjk (Chinese / Japanese / Korean)
  tf_vector  vector index on `embedding` - PREPARED BUT SWITCHED OFF
             (no embedding model chosen yet, decision 2026-10-19). Hybrid search
             ($rankFusion of tf_text + tf_vector) switches on when search.vector_enabled
             is true and documents carry embeddings.
If Atlas Search is unavailable, a simple regex search is used so nothing breaks.
"""
import logging
import re
from datetime import datetime, timezone

from pymongo import UpdateOne
from pymongo.operations import SearchIndexModel

from core import config, mongo

logger = logging.getLogger("agent")
TEXT_INDEX, VECTOR_INDEX = "tf_text", "tf_vector"


def coll():
    return mongo.db().search_docs


def setup_indexes():
    c = coll()
    c.create_index("doc_id", unique=True)
    c.create_index([("tenant_openid", 1), ("kind", 1)])
    existing = {i["name"] for i in c.list_search_indexes()}
    made = []
    if TEXT_INDEX not in existing:
        c.create_search_index(SearchIndexModel(name=TEXT_INDEX, definition={"mappings": {"dynamic": False, "fields": {
            "title": [{"type": "string", "analyzer": "lucene.standard", "multi": {"cjk": {"type": "string", "analyzer": "lucene.cjk"}}}],
            "text": [{"type": "string", "analyzer": "lucene.standard", "multi": {"cjk": {"type": "string", "analyzer": "lucene.cjk"}}}],
            "tenant_openid": {"type": "token"}, "kind": {"type": "token"}}}}))
        made.append(TEXT_INDEX)
    if VECTOR_INDEX not in existing:
        c.create_search_index(SearchIndexModel(name=VECTOR_INDEX, type="vectorSearch", definition={"fields": [
            {"type": "vector", "path": "embedding", "numDimensions": int(config.get("search.vector_dimensions", 1024)),
             "similarity": "cosine"},
            {"type": "filter", "path": "tenant_openid"}, {"type": "filter", "path": "kind"}]}))
        made.append(VECTOR_INDEX)
    return made, {i["name"]: i.get("status") for i in c.list_search_indexes()}


def upsert(docs):
    if not docs:
        return 0
    now = datetime.now(timezone.utc)
    ops = [UpdateOne({"doc_id": d["doc_id"]}, {"$set": {**d, "indexed_at": now}}, upsert=True) for d in docs]
    return coll().bulk_write(ops).upserted_count


def sync(tenant, since=None):
    """Copy searchable text from MES / agent into the corpus (safe to run again)."""
    db = mongo.db()
    q = {"tenant_openid": tenant, "note": {"$nin": ["", None]}}
    if since:
        q["ts"] = {"$gte": since}
    docs = []
    for e in db.step_events.find(q, {"_id": 0}).limit(20000):
        docs.append({"doc_id": f"ev:{e['event_id']}", "tenant_openid": tenant, "kind": f"{e['type']}_note",
                     "title": f"{e['type'].title()} {e.get('reason_code', '')} at {e.get('workstation')}",
                     "text": e["note"], "ref": e.get("batch_id", ""), "ts": e["ts"]})
    for w in db.work_orders.find({"tenant_openid": tenant}, {"_id": 0}).sort("created_at", -1).limit(2000):
        docs.append({"doc_id": f"wo:{w['wo_id']}", "tenant_openid": tenant, "kind": "work_order",
                     "title": f"{w['wo_id']} {w.get('product_name', '')}",
                     "text": f"{w.get('product_code')} {w.get('product_name', '')} {w.get('client', '')} qty {w['qty']} "
                             f"due {w['due_date']} status {w['status']}", "ref": w["wo_id"], "ts": w["created_at"]})
    for a in db.advice.find({"tenant_openid": tenant}, {"_id": 0}).limit(5000):
        docs.append({"doc_id": f"adv:{a['advice_id']}", "tenant_openid": tenant, "kind": "advice",
                     "title": a["title"], "text": f"{a['finding']} {a['suggestion']} {a.get('decision_comment', '')}",
                     "ref": a["advice_id"], "ts": a["created_at"]})
    n = upsert(docs)
    logger.info("Search sync for %s: %d docs (%d new)", tenant, len(docs), n)
    return len(docs)


def search(tenant, query, kinds=None, limit=20):
    query = (query or "").strip()
    if not query:
        return []
    filt = [{"equals": {"path": "tenant_openid", "value": tenant}}]
    if kinds:
        filt.append({"in": {"path": "kind", "value": list(kinds)}})
    stage = {"$search": {"index": TEXT_INDEX, "compound": {
        "filter": filt,
        "should": [{"text": {"query": query, "path": ["title", "text"], "fuzzy": {"maxEdits": 1}}},
                   {"text": {"query": query, "path": [{"value": "title", "multi": "cjk"}, {"value": "text", "multi": "cjk"}]}}],
        "minimumShouldMatch": 1},
        "highlight": {"path": ["text"]}}}
    proj = {"$project": {"_id": 0, "embedding": 0, "score": {"$meta": "searchScore"}, "highlights": {"$meta": "searchHighlights"}}}
    try:
        rows = list(coll().aggregate([stage, {"$limit": limit}, proj]))
        for r in rows:
            r["snippet"] = _snippet(r)
        return rows
    except Exception as exc:  # noqa: BLE001 - search must degrade, not fail
        logger.warning("Atlas Search unavailable, using simple search: %s", exc)
        rx = re.compile(re.escape(query), re.I)
        q = {"tenant_openid": tenant, "$or": [{"title": rx}, {"text": rx}]}
        if kinds:
            q["kind"] = {"$in": list(kinds)}
        rows = list(coll().find(q, {"_id": 0, "embedding": 0}).limit(limit))
        for r in rows:
            r["snippet"] = r.get("text", "")[:240]
        return rows


def _snippet(row):
    for h in row.pop("highlights", None) or []:
        parts = "".join(t["value"] for t in h.get("texts", []))
        if parts:
            return parts[:240]
    return (row.get("text") or "")[:240]
