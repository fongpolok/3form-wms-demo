"""Calendar data the PIC maintains: public holidays and per-day staffing changes.
Shift pattern and working days come from settings.yaml (aps.*), overridable in
tf_site_setting (key 'aps.shifts', 'aps.working_days')."""
from django.db import models


class Holiday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=120)
    source = models.CharField(max_length=40, default="manual")   # gov.hk | manual

    class Meta:
        db_table = "tf_holiday"
        ordering = ["date"]


class StaffingOverride(models.Model):
    """Workers available for one shift on one date (e.g. 4 people on 2026-11-02 shift B)."""
    date = models.DateField()
    shift_code = models.CharField(max_length=8)
    workers = models.IntegerField()
    note = models.CharField(max_length=200, blank=True, default="")
    updated_by = models.CharField(max_length=80, blank=True, default="")

    class Meta:
        db_table = "tf_staffing_override"
        unique_together = (("date", "shift_code"),)
        ordering = ["date", "shift_code"]
