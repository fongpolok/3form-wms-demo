from datetime import date, timedelta

from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import audit
from accounts.permissions import IsManagerOrAbove

from .excel import build_workbook, workbook_bytes

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ProductionExcelView(APIView):
    """GET /api/v1/reports/production.xlsx?from=YYYY-MM-DD&to=YYYY-MM-DD (PIC / EM)."""
    permission_classes = [IsManagerOrAbove]

    def get(self, request):
        try:
            d_to = date.fromisoformat(request.query_params.get("to") or date.today().isoformat())
            d_from = date.fromisoformat(request.query_params.get("from") or (d_to - timedelta(days=30)).isoformat())
        except ValueError:
            return Response({"detail": "Dates must look like 2026-10-19."}, status=400)
        if d_from > d_to:
            return Response({"detail": "'From' date is after 'to' date."}, status=400)
        wb, counts = build_workbook(request.user.tenant_openid, d_from, d_to)
        audit.record(request.user, "report.export", "excel", f"{d_from}..{d_to}", after=counts, request=request)
        resp = HttpResponse(workbook_bytes(wb), content_type=XLSX)
        resp["Content-Disposition"] = f'attachment; filename="3form_production_{d_from}_{d_to}.xlsx"'
        return resp
