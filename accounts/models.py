"""
People, devices, login sessions and the audit trail.

Roles, highest authority first: PIC > Eng. Manager (EM) > Worker.
- PIC / EM log in with username + password (Django auth User).
- Workers log in with a staff ID only, and only on a PIC-registered device.
- AuditLog rows can be created but never changed or deleted.
"""
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def hash_token(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_raw_token():
    return secrets.token_urlsafe(32)


class Account(models.Model):
    ROLE_PIC = "PIC"
    ROLE_EM = "EM"
    ROLE_WORKER = "WORKER"
    ROLE_CHOICES = ((ROLE_PIC, "PIC"), (ROLE_EM, "Engineering Manager"), (ROLE_WORKER, "Worker"))
    ROLE_RANK = {ROLE_WORKER: 1, ROLE_EM: 2, ROLE_PIC: 3}

    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                help_text="Password login (PIC / EM only)")
    tenant_openid = models.CharField(max_length=100, db_index=True,
                                     help_text="Links to the WMS company (userprofile.Users.openid)")
    staff_id = models.CharField(max_length=32, help_text="Badge / staff number used at workstations")
    display_name = models.CharField(max_length=80)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    legacy_staff_pk = models.BigIntegerField(null=True, blank=True,
                                             help_text="staff.ListModel id, sent as the 'operator' header to WMS endpoints")
    is_active = models.BooleanField(default=True)
    failed_logins = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tf_account"
        unique_together = (("tenant_openid", "staff_id"),)
        ordering = ["role", "display_name"]

    # DRF throttling / permission helpers treat this object as the request user.
    is_authenticated = True
    is_anonymous = False

    @property
    def rank(self):
        return self.ROLE_RANK.get(self.role, 0)

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def __str__(self):
        return f"{self.display_name} ({self.role}, {self.staff_id})"


class Device(models.Model):
    """A workstation tablet / PC registered by the PIC. Only these may open the worker page."""
    name = models.CharField(max_length=80)
    workstation = models.CharField(max_length=16)
    tenant_openid = models.CharField(max_length=100, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True)
    token_hint = models.CharField(max_length=8, help_text="First characters of the token, for identification")
    is_active = models.BooleanField(default=True)
    registered_by = models.ForeignKey(Account, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tf_device"
        ordering = ["workstation", "name"]

    def __str__(self):
        return f"{self.name} @ {self.workstation}"


class Session(models.Model):
    """One login. The raw token is only ever held by the browser; we store its hash."""
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="sessions")
    device = models.ForeignKey(Device, null=True, blank=True, on_delete=models.SET_NULL)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False)
    ip = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "tf_session"


class AuditLog(models.Model):
    """Append-only record of every change to production data: who, when, old value, new value."""
    ts = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(Account, null=True, on_delete=models.SET_NULL, related_name="+")
    actor_name = models.CharField(max_length=80)
    actor_role = models.CharField(max_length=10)
    tenant_openid = models.CharField(max_length=100, db_index=True)
    action = models.CharField(max_length=40, db_index=True)
    entity_type = models.CharField(max_length=40)
    entity_id = models.CharField(max_length=80, db_index=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    ip = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "tf_audit_log"
        ordering = ["-ts"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Audit records cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit records cannot be deleted.")
