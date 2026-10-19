"""Settings -> Integrations (PIC only): AI provider, ERP connections, read-only API keys.
Secrets go in, never come back out (only the last 4 characters are shown)."""
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import audit
from accounts import services as account_services
from accounts.models import ApiKey
from accounts.permissions import IsPIC
from core import config, secrets

from .models import AiProvider, ErpConnection


def _err(msg, code=400):
    return Response({"detail": str(msg)}, status=code)


def _https_or_local(url):
    return url.startswith("https://") or url.startswith(("http://127.0.0.1", "http://localhost"))


def _ai_payload(row):
    key = secrets.decrypt(row.api_key_enc) if row and row.api_key_enc else ""
    import os
    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    return {"label": row.label if row else "DeepSeek",
            "base_url": row.base_url if row else config.get("agent.default_base_url"),
            "model": row.model if row else config.get("agent.default_model"),
            "enabled": row.enabled if row else True, "chat_thinking": row.chat_thinking if row else True,
            "daily_call_cap": row.daily_call_cap if row else 300,
            "key_hint": secrets.mask(key) if key else (secrets.mask(env_key) + " (.env)" if env_key else ""),
            "anonymise": config.get("agent.anonymise"), "updated_by": row.updated_by if row else ""}


class AiProviderView(APIView):
    permission_classes = [IsPIC]

    def get(self, request):
        return Response(_ai_payload(AiProvider.objects.filter(tenant_openid=request.user.tenant_openid).first()))

    def put(self, request):
        d = request.data
        row, _ = AiProvider.objects.get_or_create(tenant_openid=request.user.tenant_openid)
        before = _ai_payload(row)
        for f in ("label", "base_url", "model"):
            if d.get(f):
                setattr(row, f, str(d[f]).strip())
        if not row.base_url.startswith("https://"):
            return _err("The provider address must start with https://")
        for f in ("enabled", "chat_thinking"):
            if f in d:
                setattr(row, f, bool(d[f]))
        if "daily_call_cap" in d:
            row.daily_call_cap = max(0, int(d["daily_call_cap"]))
        if d.get("api_key"):
            try:
                row.api_key_enc = secrets.encrypt(str(d["api_key"]).strip())
            except secrets.SecretError as exc:
                return _err(exc)
        if d.get("clear_api_key"):
            row.api_key_enc = ""
        row.updated_by = request.user.display_name
        row.save()
        after = _ai_payload(row)
        audit.record(request.user, "integration.ai", "ai_provider", row.pk, before=before, after=after, request=request)
        return Response(after)


class AiTestView(APIView):
    permission_classes = [IsPIC]

    def post(self, request):
        from agent import llm
        try:
            reply, model = llm.ping(request.user.tenant_openid)
            return Response({"ok": True, "reply": reply, "model": model})
        except llm.LlmUnavailable as exc:
            return Response({"ok": False, "reply": str(exc)})


def _erp_payload(c):
    hint = ""
    if c.secret_enc:
        try:
            hint = secrets.mask(secrets.decrypt(c.secret_enc))
        except secrets.SecretError:
            hint = "(cannot read – re-enter)"
    return {"id": c.pk, "name": c.name, "system": c.system, "base_url": c.base_url, "auth_type": c.auth_type,
            "username": c.username, "secret_hint": hint, "company_code": c.company_code, "enabled": c.enabled,
            "last_test_at": c.last_test_at, "last_test_result": c.last_test_result}


class ErpView(APIView):
    permission_classes = [IsPIC]

    def get(self, request):
        return Response({"connections": [_erp_payload(c) for c in ErpConnection.objects.filter(tenant_openid=request.user.tenant_openid)],
                         "systems": ErpConnection.SYSTEMS})

    def post(self, request):
        return self._save(request, ErpConnection(tenant_openid=request.user.tenant_openid))

    def put(self, request, pk=None):
        c = ErpConnection.objects.filter(pk=pk, tenant_openid=request.user.tenant_openid).first()
        if not c:
            return _err("Connection not found.", 404)
        return self._save(request, c)

    def _save(self, request, c):
        d = request.data
        before = _erp_payload(c) if c.pk else None
        if d.get("system") and d["system"] not in dict(ErpConnection.SYSTEMS):
            return _err("Unknown ERP system.")
        for f in ("name", "system", "base_url", "auth_type", "username", "company_code"):
            if f in d:
                setattr(c, f, str(d[f]).strip())
        if not c.name or not c.system:
            return _err("Name and system are required.")
        if c.base_url and not _https_or_local(c.base_url):
            return _err("The ERP address must start with https:// (http only for 127.0.0.1 / localhost tests).")
        if "enabled" in d:
            c.enabled = bool(d["enabled"])
        if d.get("secret"):
            try:
                c.secret_enc = secrets.encrypt(str(d["secret"]))
            except secrets.SecretError as exc:
                return _err(exc)
        c.updated_by = request.user.display_name
        c.save()
        audit.record(request.user, "integration.erp", "erp_connection", c.pk, before=before, after=_erp_payload(c),
                     request=request)
        return Response(_erp_payload(c), status=201 if not before else 200)

    def delete(self, request, pk=None):
        n, _ = ErpConnection.objects.filter(pk=pk, tenant_openid=request.user.tenant_openid).delete()
        audit.record(request.user, "integration.erp.delete", "erp_connection", pk, request=request)
        return Response({"deleted": n})


class ErpTestView(APIView):
    permission_classes = [IsPIC]

    def post(self, request, pk):
        from .connectors import ErpError, for_connection
        c = ErpConnection.objects.filter(pk=pk, tenant_openid=request.user.tenant_openid).first()
        if not c:
            return _err("Connection not found.", 404)
        try:
            result = "✓ " + for_connection(c).ping()
        except (ErpError, secrets.SecretError) as exc:
            result = f"✕ {exc}"
        c.last_test_at = timezone.now()
        c.last_test_result = result[:200]
        c.save(update_fields=["last_test_at", "last_test_result"])
        return Response(_erp_payload(c))


class ErpSyncView(APIView):
    """'Sync now' button: pull orders / import staff / send results immediately."""
    permission_classes = [IsPIC]

    def post(self, request):
        from .erp_sync import sync_all
        res = sync_all(force=True)
        return Response({"results": [{"connection": n, "result": {k: v if isinstance(v, (int, str)) else len(v)
                                                                   for k, v in r.items()}} for n, r in res]})


class ErpInboxView(APIView):
    permission_classes = [IsPIC]

    def get(self, request):
        from core import mongo
        status = request.query_params.get("status", "pending")
        rows = list(mongo.db().erp_inbox.find({"tenant_openid": request.user.tenant_openid, "status": status},
                                              {"_id": 0, "raw": 0}).sort("received_at", -1).limit(200))
        out = list(mongo.db().erp_outbox.find({"tenant_openid": request.user.tenant_openid},
                                              {"_id": 0}).sort("created_at", -1).limit(50))
        return Response({"inbox": rows, "outbox": out})

    def post(self, request):
        from .connectors import ErpError
        from .erp_sync import inbox_decide
        d = request.data
        try:
            wo_id = inbox_decide(request.user, d.get("erp_ref"), d.get("conn_id"), bool(d.get("approve")), d.get("edits"))
        except ErpError as exc:
            return _err(exc)
        return Response({"wo_id": wo_id})


class ApiKeysView(APIView):
    permission_classes = [IsPIC]

    def get(self, request):
        keys = ApiKey.objects.filter(account__tenant_openid=request.user.tenant_openid)
        return Response([{"id": k.pk, "name": k.name, "hint": f"••••{k.key_hint}", "is_active": k.is_active,
                          "created_by": k.created_by, "created_at": k.created_at, "last_used": k.last_used,
                          "use_count": k.use_count} for k in keys])

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        if not name:
            return _err("Give the key a name (who / what will use it).")
        key, raw = account_services.create_api_key(request.user, name, request=request)
        return Response({"id": key.pk, "name": key.name, "api_key": raw,
                         "usage": "Send header  Authorization: Api-Key <key>  to any GET endpoint. Docs: /api/docs/"},
                        status=201)


class ApiKeyRevokeView(APIView):
    permission_classes = [IsPIC]

    def post(self, request, pk):
        try:
            account_services.revoke_api_key(request.user, pk, request=request)
        except account_services.LoginError as exc:
            return _err(exc, 404)
        return Response({"revoked": pk})
