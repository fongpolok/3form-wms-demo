from datetime import date, timedelta

from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import audit
from accounts.permissions import IsManagerOrAbove, IsPIC
from core import config
from inventory.models import SiteSetting
from inventory.site import SITE

from . import calendar as cal
from . import service
from .models import Holiday, StaffingOverride


def _err(msg, code=400):
    return Response({"detail": str(msg)}, status=code)


class PlanView(APIView):
    """GET ?status=published|draft  -> the newest plan with that status (or null)."""
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        status = request.query_params.get("status", service.PUBLISHED)
        return Response(service.current(request.user.tenant_openid, status))


class ReplanView(APIView):
    permission_classes = [IsManagerOrAbove]

    def post(self, request):
        try:
            plan = service.request_replan(request.user.tenant_openid, "manual re-plan", request.user.display_name)
        except service.CuoptUnavailable as exc:
            return Response({"detail": f"No new plan: {exc} The published plan is unchanged."}, status=503)
        plan.pop("_id", None)
        return Response(plan, status=201)


class PlanDecisionView(APIView):
    permission_classes = [IsManagerOrAbove]

    def post(self, request, plan_id):
        try:
            return Response(service.decide(request.user, plan_id, bool(request.data.get("accept")), request=request))
        except ValueError as exc:
            return _err(exc)


class CalendarView(APIView):
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        shifts, days = cal.shift_settings()
        today = date.today()
        return Response({
            "shifts": shifts, "working_days": days,
            "defaults": {"shifts": config.get("aps.shifts"), "working_days": config.get("aps.working_days")},
            "holidays": list(Holiday.objects.filter(date__gte=today - timedelta(days=30)).values("date", "name", "source")),
            "staffing": list(StaffingOverride.objects.filter(date__gte=today).values()),
            "settings": {k: config.get(f"aps.{k}") for k in ("horizon_days", "changeover_minutes", "frozen_hours",
                                                              "late_buffer_hours", "workers_per_station")},
        })

    def put(self, request):
        if not IsPIC().has_permission(request, self):
            return _err("Only the PIC can change shifts.", 403)
        shifts, days = request.data.get("shifts"), request.data.get("working_days")
        try:
            for s in shifts:
                a, b = cal._minutes(s["start"]), cal._minutes(s["end"])
                if not 0 <= a < b <= 1440:
                    raise ValueError(f"Shift {s['code']}: start must be before end.")
                if s.get("break_start"):
                    bs = cal._minutes(s["break_start"])
                    if not (a <= bs and bs + int(s.get("break_minutes", 0)) <= b):
                        raise ValueError(f"Shift {s['code']}: the break must be inside the shift.")
                if int(s.get("workers", 0)) < 0:
                    raise ValueError("Workers cannot be negative.")
            if not all(isinstance(d, int) and 0 <= d <= 6 for d in days):
                raise ValueError("Working days are 0 (Mon) to 6 (Sun).")
        except (KeyError, TypeError, ValueError) as exc:
            return _err(exc)
        before = {"shifts": cal.shift_settings()[0], "working_days": cal.shift_settings()[1]}
        SiteSetting.objects.update_or_create(tenant_openid=SITE, key="aps.shifts",
                                             defaults={"value": shifts, "updated_by": request.user.display_name})
        SiteSetting.objects.update_or_create(tenant_openid=SITE, key="aps.working_days",
                                             defaults={"value": days, "updated_by": request.user.display_name})
        audit.record(request.user, "calendar.shifts", "calendar", "shifts", before=before,
                     after={"shifts": shifts, "working_days": days}, request=request)
        return Response({"shifts": shifts, "working_days": days})


class HolidayView(APIView):
    permission_classes = [IsPIC]

    def post(self, request):
        try:
            d = date.fromisoformat(request.data.get("date", ""))
        except ValueError:
            return _err("Date must look like 2026-12-24.")
        h, _ = Holiday.objects.update_or_create(date=d, defaults={"name": request.data.get("name") or "Factory holiday",
                                                                  "source": "manual"})
        audit.record(request.user, "calendar.holiday.add", "holiday", str(d), after={"name": h.name}, request=request)
        return Response({"date": d, "name": h.name}, status=201)

    def delete(self, request, day):
        n, _ = Holiday.objects.filter(date=day).delete()
        audit.record(request.user, "calendar.holiday.remove", "holiday", day, request=request)
        return Response({"deleted": n})


class StaffingView(APIView):
    permission_classes = [IsPIC]

    def post(self, request):
        try:
            d = date.fromisoformat(request.data.get("date", ""))
            workers = int(request.data.get("workers"))
        except (TypeError, ValueError):
            return _err("Date and number of workers are required.")
        code = request.data.get("shift_code", "")
        if code not in [s["code"] for s in cal.shift_settings()[0]]:
            return _err("Unknown shift.")
        StaffingOverride.objects.update_or_create(date=d, shift_code=code,
                                                  defaults={"workers": workers, "note": request.data.get("note", ""),
                                                            "updated_by": request.user.display_name})
        audit.record(request.user, "calendar.staffing", "staffing", f"{d}/{code}", after={"workers": workers},
                     request=request)
        return Response({"date": d, "shift_code": code, "workers": workers}, status=201)
