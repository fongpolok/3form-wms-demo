"""Connection settings the PIC enters on Settings -> Integrations. Secrets are encrypted (core/secrets.py)."""
from django.db import models


class AiProvider(models.Model):
    """One per company. Any OpenAI-compatible chat API (DeepSeek by default)."""
    tenant_openid = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=60, default="DeepSeek")
    base_url = models.CharField(max_length=200, default="https://api.deepseek.com")
    model = models.CharField(max_length=80, default="deepseek-v4-pro")
    api_key_enc = models.TextField(blank=True, default="")
    enabled = models.BooleanField(default=True)          # company-level "AI off" switch
    chat_thinking = models.BooleanField(default=True)    # reasoning for chat questions
    daily_call_cap = models.IntegerField(default=300)
    updated_by = models.CharField(max_length=80, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tf_ai_provider"


class ErpConnection(models.Model):
    SYSTEMS = (("SAP", "SAP"), ("ORACLE", "Oracle"), ("WORKDAY", "Workday (staff only)"), ("OTHER", "Other"))
    tenant_openid = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=80)
    system = models.CharField(max_length=10, choices=SYSTEMS)
    base_url = models.CharField(max_length=300, blank=True, default="")
    auth_type = models.CharField(max_length=20, default="basic")      # basic | oauth2 | api_key
    username = models.CharField(max_length=120, blank=True, default="")  # user / client id
    secret_enc = models.TextField(blank=True, default="")              # password / client secret / key
    company_code = models.CharField(max_length=40, blank=True, default="")  # SAP plant / Oracle org etc.
    enabled = models.BooleanField(default=False)
    last_test_at = models.DateTimeField(null=True, blank=True)
    last_test_result = models.CharField(max_length=200, blank=True, default="")
    updated_by = models.CharField(max_length=80, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tf_erp_connection"
        ordering = ["name"]
