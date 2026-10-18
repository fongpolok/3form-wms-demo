from datetime import date

from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsManagerOrAbove, IsPIC
from core import config
from goods.models import ListModel as Goods

from . import alerts, services, site
from .models import Alert, BinZone, CountTask, MaterialRequest, Product, Shipment


def _err(exc, code=400):
    return Response({"detail": str(exc)}, status=code)


def _recheck(request):
    from mes.materials import recheck_waiting
    return recheck_waiting(request.user.tenant_openid)


class StockView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        return Response(services.stock_summary(request.user.tenant_openid))


class ReceiveView(APIView):
    """Inbound: goods arrive -> stock, then waiting orders are re-checked."""
    permission_classes = [IsManagerOrAbove]

    def post(self, request):
        d = request.data
        try:
            expiry = date.fromisoformat(d["expiry_date"]) if d.get("expiry_date") else None
            lot = services.receive(request.user, d.get("goods_code", "").strip(), d.get("qty", 0),
                                   d.get("bin_name", "").strip(), d.get("lot_number", "").strip(), expiry,
                                   ref=d.get("ref", "").strip(), request=request)
        except (services.InventoryError, ValueError) as exc:
            return _err(exc)
        released = _recheck(request)
        return Response({"lot_id": lot.pk, "bin_name": lot.bin_name, "qty": lot.qty, "released_orders": released},
                        status=201)


class ShipView(APIView):
    permission_classes = [IsManagerOrAbove]

    def post(self, request):
        try:
            ship = services.ship_from_stock(request.user, request.data.get("client", ""),
                                            request.data.get("lines", []), request=request)
        except (services.InventoryError, KeyError, ValueError) as exc:
            return _err(exc)
        return Response({"shipment_id": ship.shipment_id, "lines": ship.lines}, status=201)

    def get(self, request):
        qs = Shipment.objects.filter(tenant_openid=request.user.tenant_openid)[:200]
        return Response([{"shipment_id": s.shipment_id, "client": s.client, "source": s.source, "ref": s.ref,
                          "lines": s.lines, "shipped_at": s.shipped_at, "created_by": s.created_by} for s in qs])


class PickPreviewView(APIView):
    """Which lots would be picked for an item (FEFO / FIFO), without moving anything."""
    permission_classes = [IsManagerOrAbove]

    def get(self, request, goods_code):
        lots = services.pickable_lots(request.user.tenant_openid, goods_code)
        return Response({"rule": config.industry().get("stock_rule", "fifo"),
                         "available": services.available(request.user.tenant_openid, goods_code),
                         "lots": [{"lot_number": l.lot_number, "bin_name": l.bin_name, "qty": l.qty,
                                   "expiry_date": l.expiry_date} for l in lots]})


class BinsView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        return Response({"zones": BinZone.ZONES, "bins": services.list_bins(request.user.tenant_openid),
                         "suggested_fg_bin": services.suggest_fg_bin(request.user.tenant_openid)})

    def post(self, request):
        if not IsPIC().has_permission(request, self):
            return _err("Only the PIC can add bins.", 403)
        try:
            services.create_bin(request.user, request.data.get("bin_name", "").strip(), request.data.get("zone"),
                                request.data.get("size", "Floor"), request=request)
        except services.InventoryError as exc:
            return _err(exc)
        return Response({"created": True}, status=201)


class BinZoneView(APIView):
    permission_classes = [IsPIC]

    def patch(self, request, bin_name):
        try:
            services.set_zone(request.user, bin_name, request.data.get("zone"), request=request)
        except services.InventoryError as exc:
            return _err(exc)
        return Response({"bin_name": bin_name, "zone": request.data.get("zone")})


class CountView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        qs = CountTask.objects.filter(tenant_openid=request.user.tenant_openid)[:300]
        return Response([{"id": c.pk, "bin_name": c.bin_name, "goods_code": c.goods_code, "lot_number": c.lot_number,
                          "system_qty": c.system_qty, "counted_qty": c.counted_qty,
                          "variance": c.counted_qty - c.system_qty, "status": c.status, "counted_by": c.counted_by,
                          "decided_by": c.decided_by, "created_at": c.created_at} for c in qs])

    def post(self, request):
        d = request.data
        try:
            task = services.submit_count(request.user, d.get("bin_name"), d.get("goods_code"), d.get("lot_number", ""),
                                         int(d.get("counted_qty")))
        except (TypeError, ValueError):
            return _err("Counted quantity must be a whole number.")
        return Response({"id": task.pk, "status": task.status, "variance": task.counted_qty - task.system_qty},
                        status=201)


class CountDecisionView(APIView):
    permission_classes = [IsPIC]

    def post(self, request, pk):
        try:
            task = services.decide_count(request.user, pk, bool(request.data.get("approve")), request=request)
        except services.InventoryError as exc:
            return _err(exc)
        if task.status == CountTask.APPROVED:
            _recheck(request)
        return Response({"id": task.pk, "status": task.status})


class ProductsView(APIView):
    """Products & recipes: PIC and Engineering Manager can view and edit (audited)."""
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        qs = Product.objects.filter(tenant_openid=request.user.tenant_openid).prefetch_related("recipe")
        return Response({"products": [services.product_payload(p) for p in qs],
                         "steps": config.industry()["steps"]})

    def post(self, request):
        try:
            return Response(services.save_product(request.user, request.data, request=request), status=201)
        except services.InventoryError as exc:
            return _err(exc)


class GoodsLookupView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        qs = Goods.objects.filter(openid=request.user.tenant_openid, is_delete=False)
        if q:
            qs = qs.filter(Q(goods_code__icontains=q) | Q(goods_desc__icontains=q))
        return Response(list(qs.order_by("goods_code").values("goods_code", "goods_desc", "goods_unit")[:50]))


class MaterialRequestsView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        status = request.query_params.get("status", MaterialRequest.OPEN)
        qs = MaterialRequest.objects.filter(tenant_openid=request.user.tenant_openid, status=status)
        return Response(list(qs.values()))

    def post(self, request):
        """'Re-check materials' button."""
        return Response({"released_orders": _recheck(request)})


class AlertsView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        open_only = request.query_params.get("open", "1") == "1"
        qs = Alert.objects.filter(tenant_openid=request.user.tenant_openid)
        if open_only:
            qs = qs.filter(is_open=True)
        return Response([alerts.as_dict(a) for a in qs[:200]])


class AlertAckView(APIView):
    permission_classes = [IsManagerOrAbove]

    def post(self, request, pk):
        a = alerts.acknowledge(request.user, pk, request=request)
        return Response({"acknowledged": bool(a)})


class IndustryView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        return Response({"current": site.industry_code(),
                         "options": [{"code": c, "label": config.industry(c)["label"],
                                      "stock_rule": config.industry(c).get("stock_rule")}
                                     for c in config.list_industries()]})

    def post(self, request):
        if not IsPIC().has_permission(request, self):
            return _err("Only the PIC can change the industry.", 403)
        try:
            return Response({"current": site.set_industry(request.user, request.data.get("code"), request=request)})
        except ValueError as exc:
            return _err(exc)


class MovementsView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        return Response(services.movements(request.user.tenant_openid, request.query_params.get("ref"),
                                           request.query_params.get("goods_code")))
