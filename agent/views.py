from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Account
from accounts.permissions import IsManagerOrAbove, IsPIC
from core import mongo

from . import chat, jobs, llm, search, sop


def _err(msg, code=400):
    return Response({"detail": str(msg)}, status=code)


def _human(request):
    """Chat / decisions are for people (PIC, EM), not API keys."""
    return isinstance(request.user, Account) and request.user.role in (Account.ROLE_PIC, Account.ROLE_EM)


class AdviceView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        t = request.user.tenant_openid
        status = request.query_params.get("status", "open")
        q = {"tenant_openid": t} if status == "all" else {"tenant_openid": t, "status": status}
        items = list(mongo.db().advice.find(q, {"_id": 0}).sort([("severity", 1), ("updated_at", -1)]).limit(200))
        ok, why = llm.available(t)
        last = mongo.db().agent_runs.find_one({"tenant_openid": t}, {"_id": 0}, sort=[("ts", -1)])
        return Response({"items": items, "ai_available": ok, "offline_reason": why, "last_run": last,
                         "usage": llm.usage_summary(t), "provider": {k: v for k, v in llm.provider(t).items()
                                                                     if k not in ("api_key",)}})


class AdviceRunView(APIView):
    permission_classes = [IsManagerOrAbove]

    def post(self, request):
        if not _human(request):
            return _err("Only people can run the agent.", 403)
        job = request.data.get("job")
        t = request.user.tenant_openid
        if job and job not in jobs.JOBS:
            return _err("Unknown job.")
        res = [jobs.run_job(t, job, "manual")] if job else jobs.run_all(t, "manual")
        return Response({"results": res})


class AdviceDecisionView(APIView):
    permission_classes = [IsManagerOrAbove]

    def post(self, request, advice_id):
        if not _human(request):
            return _err("Only people can accept or reject advice.", 403)
        try:
            return Response(jobs.decide(request.user, advice_id, bool(request.data.get("accept")),
                                        request.data.get("comment", "")))
        except ValueError as exc:
            return _err(exc)


class ChatView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        return Response(chat.history(request.user.tenant_openid))

    def post(self, request):
        if not _human(request):
            return _err("Chat is for the PIC and Engineering Manager.", 403)
        try:
            return Response(chat.ask(request.user, request.data.get("question", ""), request.data.get("conversation_id"),
                                     request.data.get("lang", "en")))
        except ValueError as exc:
            return _err(exc)


class SearchView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        kinds = [k for k in request.query_params.get("kinds", "").split(",") if k]
        return Response(search.search(request.user.tenant_openid, request.query_params.get("q", ""), kinds or None,
                                      int(request.query_params.get("limit", 30))))


class SopView(APIView):
    permission_classes = [IsManagerOrAbove]
    parser_classes = [MultiPartParser]

    def get(self, request):
        return Response(sop.list_docs(request.user.tenant_openid))

    def post(self, request):
        if not IsPIC().has_permission(request, self):
            return _err("Only the PIC can upload SOPs.", 403)
        f = request.FILES.get("file")
        if not f:
            return _err("Choose a file.")
        try:
            return Response(sop.upload(request.user, f, request.data.get("title", "")), status=201)
        except sop.SopError as exc:
            return _err(exc)


class SopDetailView(APIView):
    permission_classes = [IsPIC]

    def delete(self, request, sop_id):
        try:
            sop.remove(request.user, sop_id)
        except sop.SopError as exc:
            return _err(exc, 404)
        return Response({"deleted": sop_id})
