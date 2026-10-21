from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import audit
from accounts.permissions import IsManagerOrAbove, IsPIC
from core import secrets

from . import cuopt, service
from .models import OptimiserSetting


def _err(msg, code=400):
    return Response({"detail": str(msg)}, status=code)


def _payload(tenant):
    s = service.settings_for(tenant)
    return {"plan_engine": s["plan_engine"], "pick_engine": s["pick_engine"], "cuopt_url": s["cuopt_url"],
            "has_token": s["has_token"], "engines": OptimiserSetting.ENGINES}


class OptimiserView(APIView):
    """PIC: choose Built-in or cuOpt for planning and pick routes, and where cuOpt runs."""
    permission_classes = [IsPIC]

    def get(self, request):
        return Response(_payload(request.user.tenant_openid))

    def put(self, request):
        d = request.data
        tenant = request.user.tenant_openid
        before = _payload(tenant)
        row, _ = OptimiserSetting.objects.get_or_create(tenant_openid=tenant)
        engines = dict(OptimiserSetting.ENGINES)
        for f in ("plan_engine", "pick_engine"):
            if f in d:
                if d[f] not in engines:
                    return _err("Engine must be builtin or cuopt.")
                setattr(row, f, d[f])
        if "cuopt_url" in d:
            row.cuopt_url = str(d["cuopt_url"] or "").strip()
        if "cuopt" in (row.plan_engine, row.pick_engine):
            try:
                cuopt.check_url(row.cuopt_url)
            except cuopt.CuoptUnavailable as exc:
                return _err(exc)
        if d.get("cuopt_token"):
            try:
                row.cuopt_token_enc = secrets.encrypt(str(d["cuopt_token"]).strip())
            except secrets.SecretError as exc:
                return _err(exc)
        if d.get("clear_token"):
            row.cuopt_token_enc = ""
        row.updated_by = request.user.display_name
        row.save()
        after = _payload(tenant)
        audit.record(request.user, "integration.optimiser", "optimiser", row.pk, before=before, after=after,
                     request=request)
        return Response(after)


class OptimiserTestView(APIView):
    permission_classes = [IsPIC]

    def post(self, request):
        s = service.settings_for(request.user.tenant_openid)
        url = request.data.get("cuopt_url") or s["cuopt_url"]
        try:
            info = cuopt.health(url, s["cuopt_token"])
            return Response({"ok": True, "reply": f"cuOpt {info.get('version', '')} is {info.get('status', 'up')}."})
        except cuopt.CuoptUnavailable as exc:
            return Response({"ok": False, "reply": str(exc)})


class PickRouteView(APIView):
    """Ordered pick list for goods to ship: POST {"lines": [{"goods_code", "qty"}]}. Nothing is moved."""
    permission_classes = [IsManagerOrAbove]

    def post(self, request):
        lines = [l for l in (request.data.get("lines") or []) if l.get("goods_code") and int(l.get("qty") or 0) > 0]
        if not lines:
            return _err("Add at least one item with a quantity.")
        try:
            return Response(service.pick_list(request.user.tenant_openid, lines, "shipment"))
        except cuopt.CuoptUnavailable as exc:
            return _err(f"No pick route: {exc}", 503)


class OrderPickRouteView(APIView):
    """Ordered pick list for the materials of a work order's batches not yet started. Nothing is moved."""
    permission_classes = [IsManagerOrAbove]

    def get(self, request, wo_id):
        try:
            return Response(service.order_pick_list(request.user.tenant_openid, wo_id))
        except cuopt.CuoptUnavailable as exc:
            return _err(f"No pick route: {exc}", 503)
        except ValueError as exc:
            return _err(exc, 404)
