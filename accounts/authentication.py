"""
Per-person, expiring login tokens.

Header:  Authorization: Bearer <token>
Result:  request.user = Account, request.auth = the WMS company profile
         (userprofile.Users), so existing GreaterWMS views that read
         request.auth.openid keep working unchanged.
"""
import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from core import config
from userprofile.models import Users

from .models import Account, ApiKey, Session, hash_token

logger = logging.getLogger("app")
LAST_SEEN_WRITE_SECONDS = 30   # avoid a DB write on every request


def manager_idle_timeout():
    return timedelta(minutes=int(config.get("auth.manager_idle_timeout_minutes", 30)))


class TokenAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if header.startswith("Api-Key "):
            return self._api_key(request, header[len("Api-Key "):].strip())
        if not header.startswith(self.keyword + " "):
            return None  # anonymous; permission classes decide
        raw = header[len(self.keyword) + 1:].strip()
        session = (Session.objects.select_related("account", "device")
                   .filter(token_hash=hash_token(raw), revoked=False).first())
        if session is None:
            raise exceptions.AuthenticationFailed("Session not found. Please log in again.")

        now = timezone.now()
        account = session.account
        if session.expires_at <= now:
            raise exceptions.AuthenticationFailed("Session expired. Please log in again.")
        if account.role != Account.ROLE_WORKER and session.last_seen + manager_idle_timeout() <= now:
            session.revoked = True
            session.save(update_fields=["revoked"])
            logger.info("Idle timeout for %s", account)
            raise exceptions.AuthenticationFailed("Logged out after inactivity. Please log in again.")
        if not account.is_active:
            raise exceptions.AuthenticationFailed("Account disabled.")
        if session.device_id and not session.device.is_active:
            raise exceptions.AuthenticationFailed("This device is no longer authorised.")

        if (now - session.last_seen).total_seconds() > LAST_SEEN_WRITE_SECONDS:
            session.last_seen = now
            session.save(update_fields=["last_seen"])

        tenant = Users.objects.filter(openid=account.tenant_openid, is_delete=False).first()
        if tenant is None:
            raise exceptions.AuthenticationFailed("Company profile missing for this account.")
        request.tf_session = session
        return account, tenant

    def _api_key(self, request, raw):
        key = ApiKey.objects.select_related("account").filter(key_hash=hash_token(raw), is_active=True).first()
        if key is None or not key.account.is_active:
            raise exceptions.AuthenticationFailed("API key not valid or revoked.")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            logger.warning("Blocked write with read-only API key %s: %s %s", key.name, request.method, request.path)
            raise exceptions.PermissionDenied("API keys are read-only.")
        now = timezone.now()
        ApiKey.objects.filter(pk=key.pk).update(last_used=now, use_count=key.use_count + 1)
        logging.getLogger("audit").info("API key %s read %s", key.name, request.path)
        tenant = Users.objects.filter(openid=key.account.tenant_openid, is_delete=False).first()
        request.tf_session = None
        return key.account, tenant

    def authenticate_header(self, request):
        return self.keyword
