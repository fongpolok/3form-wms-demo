"""Site-level runtime settings that the PIC can change on screen (stored in
tf_site_setting, falling back to config/settings.yaml)."""
import time

from accounts import audit
from core import config

from .models import SiteSetting

SITE = ""          # one deployment = one site; settings are site-wide
_cache = {"industry": (None, 0.0)}
CACHE_SECONDS = 10


def get_setting(key, default=None):
    row = SiteSetting.objects.filter(tenant_openid=SITE, key=key).first()
    return row.value if row else default


def industry_code():
    value, at = _cache["industry"]
    if time.time() - at < CACHE_SECONDS:
        return value
    value = get_setting("industry") or config.get("site.industry", "general")
    _cache["industry"] = (value, time.time())
    return value


def set_industry(account, code, request=None):
    if code not in config.list_industries():
        raise ValueError(f"Unknown industry '{code}'.")
    before = industry_code()
    SiteSetting.objects.update_or_create(tenant_openid=SITE, key="industry",
                                         defaults={"value": code, "updated_by": account.display_name})
    _cache["industry"] = (code, time.time())
    audit.record(account, "settings.industry", "site_setting", "industry", before={"industry": before},
                 after={"industry": code}, request=request)
    return code
