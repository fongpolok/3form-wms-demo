"""
Public website demo mode (environment variable PUBLIC_DEMO=1).

Anyone on the internet can sign in, so:
  - one-click "Try it" sign-in as the demo PIC / Engineering Manager / worker tablet
    (no passwords are shown or needed);
  - risky settings are refused (AI key, ERP connections, API keys, people, tablets,
    SOP uploads, old GreaterWMS screens): see public_demo.blocked_writes in settings.yaml;
  - the AI is capped at public_demo.ai_daily_calls per day;
  - all data is wiped and re-created every day (manage.py public_demo_reset).
Never switch this on for a client install.
"""
import hashlib
import hmac
import logging
import os

from django.conf import settings
from django.http import JsonResponse

from core import config

logger = logging.getLogger("app")
SAFE = ("GET", "HEAD", "OPTIONS")
REFUSED = "Switched off in the public demo. Everything else can be tried."
REFUSED_ZH = "公開示範版已關閉此功能，其他功能均可試用。"


def enabled():
    return os.environ.get("PUBLIC_DEMO", "").strip().lower() in ("1", "true", "yes", "on")


def device_token(workstation):
    """Fixed demo tablet token per workstation, re-created from SECRET_KEY (never stored in clear)."""
    msg = f"public-demo-device:{workstation}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def write_refused(method, path):
    if method in SAFE:
        return False
    if any(path.startswith(p) for p in config.get("public_demo.blocked_writes", [])):
        return True
    if not config.get("public_demo.allow_writes_outside_api", False) and not path.startswith("/api/v1/"):
        return True
    return False


class PublicDemoGuardMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if enabled() and write_refused(request.method, request.path):
            logger.info("Public demo: refused %s %s", request.method, request.path)
            return JsonResponse({"detail": REFUSED, "detail_zh": REFUSED_ZH, "status_code": 403}, status=403)
        return self.get_response(request)
