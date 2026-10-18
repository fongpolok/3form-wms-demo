"""Legacy GreaterWMS stock endpoints are read-only from v3.2.0: every stock
movement must go through the new inventory ledger (/api/v1/inventory/...),
otherwise the two records would drift apart."""
import logging

from django.http import JsonResponse

logger = logging.getLogger("app")
LEGACY_STOCK_PREFIXES = ("/asn/", "/dn/", "/stock/", "/cyclecount/")
SAFE = ("GET", "HEAD", "OPTIONS")


class LegacyStockReadOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in SAFE and request.path.startswith(LEGACY_STOCK_PREFIXES):
            logger.warning("Blocked legacy stock write %s %s", request.method, request.path)
            return JsonResponse({"detail": "This legacy endpoint is read-only. Use /api/v1/inventory/ instead.",
                                 "status_code": 410}, status=410)
        return self.get_response(request)
