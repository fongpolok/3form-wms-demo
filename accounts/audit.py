"""Write audit-trail entries. Every PIC edit of WIP / scrap goes through `record`."""
import json
import logging

from .models import AuditLog

logger = logging.getLogger("audit")


def client_ip(request):
    if request is None:
        return ""
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")) or ""


def record(actor, action, entity_type, entity_id, before=None, after=None, reason="", request=None,
           tenant_openid=None):
    entry = AuditLog.objects.create(
        actor=actor,
        actor_name=getattr(actor, "display_name", "system"),
        actor_role=getattr(actor, "role", "SYSTEM"),
        tenant_openid=tenant_openid or getattr(actor, "tenant_openid", ""),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before=before,
        after=after,
        reason=reason or "",
        ip=client_ip(request),
    )
    logger.info("AUDIT %s %s %s by %s: before=%s after=%s reason=%r",
                action, entity_type, entity_id, entry.actor_name,
                json.dumps(before, default=str), json.dumps(after, default=str), reason)
    return entry
