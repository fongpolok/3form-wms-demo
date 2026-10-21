from django.db import models


class OptimiserSetting(models.Model):
    """One per company: which engine plans production / orders pick routes, and where cuOpt runs."""
    BUILTIN, CUOPT = "builtin", "cuopt"
    ENGINES = ((BUILTIN, "Built-in"), (CUOPT, "NVIDIA cuOpt"))
    tenant_openid = models.CharField(max_length=100, unique=True)
    plan_engine = models.CharField(max_length=10, choices=ENGINES, default=BUILTIN)
    pick_engine = models.CharField(max_length=10, choices=ENGINES, default=BUILTIN)
    cuopt_url = models.CharField(max_length=200, blank=True, default="")      # e.g. http://10.0.0.5:5000
    cuopt_token_enc = models.TextField(blank=True, default="")                  # optional, encrypted
    updated_by = models.CharField(max_length=80, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tf_optimiser_setting"
