"""
Provider-neutral LLM client: any OpenAI-compatible /chat/completions API
(DeepSeek by default; the PIC can point it at another provider in Settings).

    available(tenant)  -> (True, None) or (False, "reason shown as 'Advisor offline'")
    chat(tenant, messages, tools=None, thinking=False, max_tokens=..., purpose="job")

Every call is counted against the company's daily cap and its tokens logged
(Mongo `llm_usage`). A failure never breaks the caller: it raises LlmUnavailable,
and callers fall back to plain calculations.
"""
import logging
import os
from datetime import datetime, timezone

import requests

from core import config, mongo, secrets

logger = logging.getLogger("agent")


class LlmUnavailable(Exception):
    pass


def provider(tenant):
    """Settings for this company: DB (PIC) first, then .env / settings.yaml defaults."""
    from integrations.models import AiProvider
    row = AiProvider.objects.filter(tenant_openid=tenant).first()
    key = ""
    if row and row.api_key_enc:
        key = secrets.decrypt(row.api_key_enc)
    key = key or os.environ.get("DEEPSEEK_API_KEY", "")
    return {
        "label": row.label if row else "DeepSeek",
        "base_url": (row.base_url if row else config.get("agent.default_base_url")).rstrip("/"),
        "model": row.model if row else config.get("agent.default_model"),
        "api_key": key,
        "enabled": (row.enabled if row else True) and bool(config.get("agent.enabled", True)),
        "chat_thinking": row.chat_thinking if row else True,
        "daily_call_cap": row.daily_call_cap if row else 300,
        "key_source": "settings" if (row and row.api_key_enc) else (".env" if key else "none"),
    }


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def calls_today(tenant):
    doc = mongo.db().llm_usage.find_one({"_id": f"{tenant}:{_today()}"})
    return doc.get("calls", 0) if doc else 0


def available(tenant):
    p = provider(tenant)
    if not p["enabled"]:
        return False, "AI is switched off for this company (Settings → Integrations)."
    if not p["api_key"]:
        return False, "No AI API key. Add one in Settings → Integrations."
    if calls_today(tenant) >= int(p["daily_call_cap"]):
        return False, f"Daily AI limit reached ({p['daily_call_cap']} calls). Plain calculations only until tomorrow."
    return True, None


def _log_usage(tenant, model, purpose, usage):
    db = mongo.db()
    day = _today()
    inc = {"calls": 1, "prompt_tokens": usage.get("prompt_tokens", 0),
           "completion_tokens": usage.get("completion_tokens", 0), f"by_purpose.{purpose}": 1}
    db.llm_usage.update_one({"_id": f"{tenant}:{day}"}, {"$inc": inc, "$set": {"tenant_openid": tenant, "day": day,
                                                                                 "model": model}}, upsert=True)


def chat(tenant, messages, tools=None, thinking=False, max_tokens=1200, purpose="job", response_json=False):
    ok, why = available(tenant)
    if not ok:
        raise LlmUnavailable(why)
    p = provider(tenant)
    body = {"model": p["model"], "messages": messages, "max_tokens": int(max_tokens)}
    if not thinking:
        body["thinking"] = {"type": "disabled"}     # DeepSeek V4: cheaper, faster structured answers
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if response_json:
        body["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(f"{p['base_url']}/chat/completions", json=body, timeout=float(config.get("agent.timeout_seconds", 90)),
                          headers={"Authorization": f"Bearer {p['api_key']}", "Content-Type": "application/json"})
    except requests.RequestException as exc:
        logger.warning("LLM request failed: %s", exc)
        raise LlmUnavailable(f"Cannot reach {p['label']} ({exc.__class__.__name__}).")
    if r.status_code != 200:
        detail = r.text[:300]
        logger.warning("LLM HTTP %s: %s", r.status_code, detail)
        raise LlmUnavailable(f"{p['label']} answered {r.status_code}. See logs/agent.log.")
    data = r.json()
    _log_usage(tenant, p["model"], purpose, data.get("usage") or {})
    msg = data["choices"][0]["message"]
    logger.info("LLM %s %s: %s tokens, finish=%s", p["model"], purpose, (data.get("usage") or {}).get("total_tokens"),
                data["choices"][0].get("finish_reason"))
    return {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or [],
            "reasoning": msg.get("reasoning_content"), "usage": data.get("usage") or {}, "model": p["model"],
            "finish": data["choices"][0].get("finish_reason"),
            "raw_message": msg}


def usage_summary(tenant, days=31):
    rows = list(mongo.db().llm_usage.find({"tenant_openid": tenant}, {"_id": 0}).sort("day", -1).limit(days))
    return {"today_calls": calls_today(tenant), "days": rows,
            "month_calls": sum(r.get("calls", 0) for r in rows),
            "month_tokens": sum(r.get("prompt_tokens", 0) + r.get("completion_tokens", 0) for r in rows)}


def ping(tenant):
    """Settings 'Test connection' button."""
    out = chat(tenant, [{"role": "user", "content": "Reply with the single word: pong"}], max_tokens=10, purpose="test")
    return out["content"].strip(), out["model"]
