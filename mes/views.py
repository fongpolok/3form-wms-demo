import hmac
import logging
import os
from datetime import datetime

from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Account
from accounts.permissions import IsManagerOrAbove, IsPIC, IsWorkerOrAbove
from accounts.services import device_from_token
from core import config, mongo
from core.ids import new_event_id

from . import devices, lean, services
from .workstations import list_workstations

logger = logging.getLogger("app")


def _error(exc, code=400):
    return Response({"detail": str(exc)}, status=code)


def _device(request):
    return getattr(request, "tf_session", None) and request.tf_session.device


def _check_station(request, workstation):
    """A worker tablet may only act for its own workstation."""
    device = _device(request)
    if device is not None and device.workstation != workstation:
        return Response({"detail": f"This device belongs to {device.workstation}."}, status=403)
    return None


class WorkstationListView(APIView):
    permission_classes = [IsWorkerOrAbove]

    def get(self, request):
        return Response(list_workstations())


class WorkerBoardView(APIView):
    permission_classes = [IsWorkerOrAbove]

    def get(self, request, ws):
        denied = _check_station(request, ws)
        if denied:
            return denied
        try:
            return Response(services.worker_board(request.user.tenant_openid, ws))
        except services.MesError as exc:
            return _error(exc, 404)


class WorkerActionView(APIView):
    """One endpoint per button: start / finish / scrap / stop / resume / measure."""
    permission_classes = [IsWorkerOrAbove]

    def post(self, request, ws, action):
        denied = _check_station(request, ws)
        if denied:
            return denied
        d = request.data
        event_id = d.get("event_id") or new_event_id()
        kw = {"device": _device(request), "client_ts": d.get("client_ts")}
        try:
            if action == "start":
                result = services.start_step(request.user, ws, d.get("batch_id", "").strip(), event_id, **kw)
            elif action == "finish":
                result = services.finish_step(request.user, ws, d.get("good_qty"), event_id, **kw)
            elif action == "scrap":
                result = services.record_scrap(request.user, ws, d.get("qty"), d.get("reason_code"), event_id,
                                               note=d.get("note", ""), **kw)
            elif action == "stop":
                result = services.machine_stop(request.user, ws, d.get("reason_code"), event_id,
                                               note=d.get("note", ""), **kw)
            elif action == "resume":
                result = services.machine_resume(request.user, ws, event_id, **kw)
            elif action == "measure":
                result = services.record_measurement(request.user, ws, d.get("value"), event_id, **kw)
            elif action == "putaway":
                result = services.put_away(request.user, ws, d.get("bin", ""), event_id, device=kw["device"])
            else:
                return _error("Unknown action.", 404)
        except services.MesError as exc:
            return _error(exc)
        return Response(result)


class ScanFeedView(APIView):
    """Worker page polls this for barcodes read by the workstation's scanner.

    Also readable by a registered device before anyone logs in, so a worker
    can sign in by scanning their staff badge (own workstation only).
    """
    permission_classes = [AllowAny]

    def get(self, request, ws):
        if isinstance(request.user, Account):
            denied = _check_station(request, ws)
            if denied:
                return denied
        else:
            device = device_from_token(request.META.get("HTTP_X_DEVICE_TOKEN", ""))
            if device is None or device.workstation != ws:
                return _error("Device not authorised for this workstation.", 403)
        after = request.query_params.get("after")
        after_ts = datetime.fromisoformat(after.replace("Z", "+00:00")) if after else None
        return Response(services.scans_since(ws, after_ts))


class WorkOrderListView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        return Response(services.list_work_orders(request.user.tenant_openid, request.query_params.get("status")))

    def post(self, request):
        if not IsPIC().has_permission(request, self):
            return _error("Only the PIC can create work orders.", 403)
        try:
            wo, batches = services.create_work_order(request.user, request.data, source="PIC", request=request)
        except services.MesError as exc:
            return _error(exc)
        return Response({"work_order": wo, "batches": batches}, status=201)


class StationStatusView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        return Response(services.station_status(request.user.tenant_openid))


class ProgressView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        return Response(services.progress_overview(request.user.tenant_openid))


class WipListView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        q = {"tenant_openid": request.user.tenant_openid}
        for f in ("batch_id", "wo_id", "workstation", "status"):
            if request.query_params.get(f):
                q[f] = request.query_params[f]
        return Response(list(mongo.db().wip.find(q, {"_id": 0}).sort("started_at", -1).limit(500)))


class WipEditView(APIView):
    permission_classes = [IsPIC]

    def patch(self, request, wip_id):
        try:
            return Response(services.pic_edit_wip(request.user, wip_id, request.data.get("changes", {}),
                                                  request.data.get("reason", ""), request=request))
        except (services.MesError, ValueError) as exc:
            return _error(exc)


class EventListView(APIView):
    """Scrap trace-back and step history (EM / PIC only — never shown to workers)."""
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        q = {"tenant_openid": request.user.tenant_openid}
        for f in ("wip_id", "batch_id", "wo_id", "type", "workstation"):
            if request.query_params.get(f):
                q[f] = request.query_params[f]
        return Response(list(mongo.db().step_events.find(q, {"_id": 0}).sort("ts", -1).limit(1000)))


class EventEditView(APIView):
    permission_classes = [IsPIC]

    def patch(self, request, event_id):
        try:
            return Response(services.pic_edit_event(request.user, event_id, request.data.get("changes", {}),
                                                    request.data.get("reason", ""), request=request))
        except services.MesError as exc:
            return _error(exc)


class SettingsView(APIView):
    """Read-only view of tunable settings + industry presets for the PIC screen."""
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        return Response({"settings": {k: v for k, v in config.all_settings().items() if k != "demo"},
                         "industries": config.list_industries(),
                         "industry": config.industry()})


# ------------------------------------------------------------------ gateway
class HasGatewayToken(BasePermission):
    def has_permission(self, request, view):
        expected = os.environ.get("GATEWAY_TOKEN", "")
        given = request.META.get("HTTP_X_GATEWAY_TOKEN", "")
        return bool(expected) and hmac.compare_digest(expected, given)


class GatewayScanView(APIView):
    authentication_classes = []
    permission_classes = [HasGatewayToken]

    def post(self, request):
        d = request.data
        if not d.get("event_id") or not d.get("code") or not d.get("workstation"):
            return _error("event_id, workstation and code are required.")
        return Response(services.record_gateway_scan(d["event_id"], d.get("device_id", ""), d["workstation"],
                                                     d["code"], d.get("ts")))


class GatewayHeartbeatView(APIView):
    authentication_classes = []
    permission_classes = [HasGatewayToken]

    def post(self, request):
        return Response(services.record_heartbeat(request.data.get("gateway_id", "gateway"),
                                                  request.data.get("devices", [])))


class GatewayVisionView(APIView):
    """Camera result line, e.g. PASS or FAIL,<reason> (camera does the image processing)."""
    authentication_classes = []
    permission_classes = [HasGatewayToken]

    def post(self, request):
        d = request.data
        if not d.get("event_id") or not d.get("workstation") or str(d.get("result", "")).upper() not in ("PASS", "FAIL"):
            return _error("event_id, workstation and result (PASS/FAIL) are required.")
        return Response(devices.record_vision_result(d["event_id"], d.get("device_id", ""), d["workstation"],
                                                     d["result"], d.get("reason", "")))


class GatewayRackView(APIView):
    authentication_classes = []
    permission_classes = [HasGatewayToken]

    def post(self, request):
        d = request.data
        if not d.get("event_id") or not d.get("bin_name") or not d.get("observed"):
            return _error("event_id, bin_name and observed are required.")
        return Response(devices.record_rack_report(d["event_id"], d.get("device_id", ""), d["bin_name"],
                                                   d["observed"]))


def _dates(request):
    from datetime import date, timedelta
    d_to = date.fromisoformat(request.query_params.get("to") or date.today().isoformat())
    d_from = date.fromisoformat(request.query_params.get("from") or (d_to - timedelta(days=30)).isoformat())
    return d_from, d_to


class LeanView(APIView):
    """OEE, yields, DPMO / sigma and scrap Pareto for a date range (EM / PIC)."""
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        try:
            d_from, d_to = _dates(request)
        except ValueError:
            return _error("Dates must look like 2026-10-19.")
        t = request.user.tenant_openid
        return Response({"from": d_from, "to": d_to, "oee": lean.oee(t, d_from, d_to),
                         "yields": lean.yields(t, d_from, d_to),
                         "pareto": lean.pareto(t, d_from, d_to, request.query_params.get("workstation"))})


class SpcView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        return Response(lean.spc(request.user.tenant_openid, request.query_params.get("step"),
                                 request.query_params.get("points")))


class HealthView(APIView):
    """Open endpoint: screens ping it every few seconds to drive the network alarm."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        return Response({"server": True, "mongo": mongo.ping(),
                         "alarm_timeout_seconds": int(config.get("network_alarm.timeout_seconds", 10)),
                         "alarm_sound": bool(config.get("network_alarm.sound", True)),
                         "worker_poll_interval_ms": int(config.get("network_alarm.worker_poll_interval_ms", 1000)),
                         "heartbeat_interval_seconds": int(config.get("network_alarm.heartbeat_interval_seconds", 3))})
