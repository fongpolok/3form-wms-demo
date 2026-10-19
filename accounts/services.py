"""
Login, device and account rules (no request/response handling here, so the
same functions serve the API, management commands and tests).
"""
import logging
from datetime import timedelta

from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone

from core import config

from . import audit
from .models import Account, Device, Session, hash_token, new_raw_token

logger = logging.getLogger("app")


class LoginError(Exception):
    """Shown to the user as-is, so keep the wording plain."""


def _register_failure(account):
    account.failed_logins += 1
    if account.failed_logins >= int(config.get("auth.max_failed_logins", 5)):
        account.locked_until = timezone.now() + timedelta(minutes=int(config.get("auth.lockout_minutes", 15)))
        account.failed_logins = 0
        logger.warning("Account locked after repeated failures: %s", account)
    account.save(update_fields=["failed_logins", "locked_until"])


def _open_session(account, hours=None, device=None, ip=""):
    raw = new_raw_token()
    if hours is None:
        # PIC / EM: hard cap of one working day; idle timeout is enforced per request.
        hours = 12
    Session.objects.create(account=account, device=device, token_hash=hash_token(raw),
                           expires_at=timezone.now() + timedelta(hours=hours), ip=ip)
    return raw


def password_login(username, password, ip=""):
    account = Account.objects.select_related("user").filter(user__username=username).first()
    if account is None or account.role == Account.ROLE_WORKER:
        logger.info("Password login refused for unknown/worker username %r", username)
        raise LoginError("Wrong username or password.")
    if account.is_locked():
        raise LoginError("Account locked after too many attempts. Try again later or ask the PIC.")
    if not account.is_active or authenticate(username=username, password=password) is None:
        _register_failure(account)
        raise LoginError("Wrong username or password.")
    account.failed_logins = 0
    account.save(update_fields=["failed_logins"])
    logger.info("Password login: %s from %s", account, ip)
    return account, _open_session(account, ip=ip)


def device_from_token(raw_device_token):
    if not raw_device_token:
        return None
    return Device.objects.filter(token_hash=hash_token(raw_device_token), is_active=True).first()


def worker_login(staff_id, raw_device_token, ip=""):
    device = device_from_token(raw_device_token)
    if device is None:
        raise LoginError("Device not authorised. Ask the PIC to register this workstation.")
    # Only people can sign in at a workstation: never API-key or system (ERP connector) accounts.
    account = Account.objects.filter(tenant_openid=device.tenant_openid, staff_id=str(staff_id).strip(), is_active=True,
                                     role__in=[Account.ROLE_WORKER, Account.ROLE_EM, Account.ROLE_PIC]).first()
    if account is None:
        logger.info("Unknown staff ID %r on device %s", staff_id, device)
        raise LoginError("Staff ID not found.")
    device.last_seen = timezone.now()
    device.save(update_fields=["last_seen"])
    logger.info("Worker login: %s on %s", account, device)
    raw = _open_session(account, hours=int(config.get("auth.worker_session_hours", 12)), device=device, ip=ip)
    return account, device, raw


def logout(session):
    session.revoked = True
    session.save(update_fields=["revoked"])


@transaction.atomic
def register_device(pic, name, workstation, request=None):
    raw = new_raw_token()
    device = Device.objects.create(name=name, workstation=workstation, tenant_openid=pic.tenant_openid,
                                   token_hash=hash_token(raw), token_hint=raw[:6], registered_by=pic)
    audit.record(pic, "device.register", "device", device.pk, after={"name": name, "workstation": workstation},
                 request=request)
    return device, raw


@transaction.atomic
def set_device_active(pic, device, active, request=None):
    before = {"is_active": device.is_active}
    device.is_active = active
    device.save(update_fields=["is_active"])
    if not active:
        Session.objects.filter(device=device, revoked=False).update(revoked=True)
    audit.record(pic, "device.activate" if active else "device.revoke", "device", device.pk,
                 before=before, after={"is_active": active}, request=request)


@transaction.atomic
def create_api_key(pic, name, request=None):
    """New read-only key. The raw key is returned once; only its hash is stored."""
    from .models import ApiKey
    n = Account.objects.filter(tenant_openid=pic.tenant_openid, role=Account.ROLE_AGENT).count() + 1
    acct = Account.objects.create(tenant_openid=pic.tenant_openid, staff_id=f"API-{n:03d}-{new_raw_token()[:4]}",
                                  display_name=f"API: {name}", role=Account.ROLE_AGENT)
    raw = "tfk_" + new_raw_token()
    key = ApiKey.objects.create(account=acct, name=name, key_hash=hash_token(raw), key_hint=raw[-4:],
                                created_by=pic.display_name)
    audit.record(pic, "api_key.create", "api_key", key.pk, after={"name": name}, request=request)
    return key, raw


@transaction.atomic
def revoke_api_key(pic, key_id, request=None):
    from .models import ApiKey
    key = ApiKey.objects.select_related("account").filter(pk=key_id, account__tenant_openid=pic.tenant_openid).first()
    if key is None:
        raise LoginError("API key not found.")
    key.is_active = False
    key.save(update_fields=["is_active"])
    key.account.is_active = False
    key.account.save(update_fields=["is_active"])
    audit.record(pic, "api_key.revoke", "api_key", key.pk, after={"name": key.name}, request=request)
    return key
