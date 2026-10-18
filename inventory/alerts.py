"""Alerts for PIC / EM (alerts bell). Same dedupe_key while open = no duplicate."""
import logging

from django.utils import timezone

from accounts import audit

from .models import Alert

logger = logging.getLogger("app")


def raise_alert(tenant, kind, title, detail="", ref="", severity="warn", dedupe_key="", is_demo=False):
    if dedupe_key and Alert.objects.filter(tenant_openid=tenant, dedupe_key=dedupe_key, is_open=True).exists():
        return None
    a = Alert.objects.create(tenant_openid=tenant, kind=kind, severity=severity, title=title, detail=detail, ref=ref,
                             dedupe_key=dedupe_key, is_demo=is_demo)
    logger.warning("ALERT %s [%s] %s - %s", kind, severity, title, detail)
    return a


def close_alerts(tenant, dedupe_key, by="system"):
    n = Alert.objects.filter(tenant_openid=tenant, dedupe_key=dedupe_key, is_open=True).update(
        is_open=False, acknowledged_by=by, acknowledged_at=timezone.now())
    return n


def acknowledge(account, alert_id, request=None):
    a = Alert.objects.filter(pk=alert_id, tenant_openid=account.tenant_openid, is_open=True).first()
    if a is None:
        return None
    a.is_open, a.acknowledged_by, a.acknowledged_at = False, account.display_name, timezone.now()
    a.save()
    audit.record(account, "alert.acknowledge", "alert", a.pk, after={"kind": a.kind, "title": a.title},
                 request=request)
    return a


def as_dict(a):
    return {"id": a.id, "kind": a.kind, "severity": a.severity, "title": a.title, "detail": a.detail, "ref": a.ref,
            "is_open": a.is_open, "created_at": a.created_at, "acknowledged_by": a.acknowledged_by}
