"""
Ask-the-agent chat (PIC + Engineering Manager). The AI may call the read-only
tools in agent/tools.py (max agent.max_tool_rounds look-ups), then answers with
the numbers it used. Everything it sees is anonymised; names are restored in the
saved answer. Conversations are stored in Mongo `agent_chats`.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from core import config, mongo

from . import llm, tools
from .anonymise import Anonymiser

logger = logging.getLogger("agent")

SYSTEM = (
    "You are the advisory AI of a factory production system (MES + WMS + APS). You can only READ data through the "
    "tools; you can never change orders, stock, plans or records, and you must say so if asked to. Look things up "
    "before answering, quote the numbers you used and say which tool they came from. Use Lean / Six Sigma ideas "
    "(DMAIC, Pareto, 5-Whys, SMED, SPC/Cpk) when useful. If data is missing, say what is missing. Keep answers short "
    "and practical. Names like 'Client A' or 'Worker 3' are placeholders; keep them as they are. "
    "Answer in the user's language: {lang}.")


def ask(account, question, conversation_id=None, lang="en"):
    t = account.tenant_openid
    db = mongo.db()
    question = (question or "").strip()
    if not question:
        raise ValueError("Please type a question.")
    conv = db.agent_chats.find_one({"conversation_id": conversation_id, "tenant_openid": t}) if conversation_id else None
    if conv is None:
        conv = {"conversation_id": f"CHAT-{uuid.uuid4().hex[:8].upper()}", "tenant_openid": t,
                "started_by": account.display_name, "created_at": datetime.now(timezone.utc), "turns": []}
        db.agent_chats.insert_one(dict(conv))
    ok, why = llm.available(t)
    if not ok:
        turn = {"q": question, "a": f"Advisor offline: {why}", "tools": [], "source": "offline",
                "asked_by": account.display_name, "ts": datetime.now(timezone.utc)}
        db.agent_chats.update_one({"conversation_id": conv["conversation_id"]}, {"$push": {"turns": turn}})
        return {"conversation_id": conv["conversation_id"], **turn}

    anon = Anonymiser(t)
    p = llm.provider(t)
    lang_name = "Traditional Chinese (Hong Kong)" if lang == "zh-hant" else "English"
    messages = [{"role": "system", "content": SYSTEM.format(lang=lang_name)}]
    for old in conv.get("turns", [])[-4:]:          # short memory of this conversation
        messages += [{"role": "user", "content": anon.text(old["q"])}, {"role": "assistant", "content": anon.text(old["a"])}]
    messages.append({"role": "user", "content": anon.text(question)})
    catalogue = [spec for _, spec in tools.TOOLS.values()]
    used = []
    thinking = bool(p["chat_thinking"])
    answer, model = "", p["model"]
    for _round in range(int(config.get("agent.max_tool_rounds", 5)) + 1):
        try:
            out = llm.chat(t, messages, tools=catalogue, thinking=thinking,
                           max_tokens=int(config.get("agent.chat_max_tokens", 2000)), purpose="chat")
        except llm.LlmUnavailable as exc:
            if thinking and used:                     # some providers reject thinking + tool results: retry plain
                thinking = False
                continue
            answer = f"Advisor offline: {exc}"
            break
        model = out["model"]
        if not out["tool_calls"]:
            if not out["content"].strip() and out.get("finish") == "length" and thinking:
                thinking = False          # reasoning used the whole budget: answer again without it
                continue
            answer = out["content"].strip() or "The answer was cut off. Please ask a narrower question."
            break
        messages.append({"role": "assistant", "content": out["content"] or "", "tool_calls": out["tool_calls"]})
        for tc in out["tool_calls"]:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            result = anon.apply(tools.call(t, name, args))
            used.append({"tool": name, "args": args})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result, default=str)[:12000]})
    else:
        answer = answer or "I needed more look-ups than allowed. Please ask a narrower question."
    turn = {"q": question, "a": anon.restore(answer), "tools": used, "source": "ai", "model": model,
            "asked_by": account.display_name, "ts": datetime.now(timezone.utc)}
    db.agent_chats.update_one({"conversation_id": conv["conversation_id"]}, {"$push": {"turns": turn}})
    logger.info("Chat %s by %s: %d tool call(s)", conv["conversation_id"], account.display_name, len(used))
    return {"conversation_id": conv["conversation_id"], **turn}


def history(tenant, limit=20):
    return list(mongo.db().agent_chats.find({"tenant_openid": tenant}, {"_id": 0}).sort("created_at", -1).limit(limit))
