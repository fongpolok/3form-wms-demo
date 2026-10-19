"""
Working calendar as a grid of slots (default 5 minutes).

A slot is working when its day is a working day, it is not a holiday, it falls
inside a shift and not inside that shift's break. Each working slot carries
the number of workers that shift has (default from settings, or a per-date
override set by the PIC).
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core import config


@dataclass
class Slot:
    start: datetime          # timezone-aware, site time zone
    working: bool
    shift: str = ""
    workers: int = 0


def tz():
    return ZoneInfo(config.get("site.timezone", "Asia/Hong_Kong"))


def _minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def shift_settings():
    """Shift pattern + working days: DB override (PIC) first, then settings.yaml."""
    from inventory.site import get_setting
    shifts = get_setting("aps.shifts") or config.get("aps.shifts", [])
    days = get_setting("aps.working_days")
    if days is None:
        days = config.get("aps.working_days", [0, 1, 2, 3, 4, 5])
    return shifts, days


def holidays_between(d0, d1):
    from .models import Holiday
    return {h.date: h.name for h in Holiday.objects.filter(date__gte=d0, date__lte=d1)}


def staffing_between(d0, d1):
    from .models import StaffingOverride
    return {(s.date, s.shift_code): s.workers for s in StaffingOverride.objects.filter(date__gte=d0, date__lte=d1)}


def minute_profile(shifts):
    """For one working day: minute-of-day -> (shift code, default workers) or None."""
    prof = {}
    for s in shifts:
        a, b = _minutes(s["start"]), _minutes(s["end"])
        brk = _minutes(s["break_start"]) if s.get("break_start") else None
        brk_end = brk + int(s.get("break_minutes", 0)) if brk is not None else None
        for m in range(a, b):
            if brk is not None and brk <= m < brk_end:
                continue
            prof[m] = (s["code"], int(s.get("workers", 0)))
    return prof


def build(start, days=None, slot_minutes=None, shifts=None, working_days=None, holidays=None, staffing=None):
    """Slots from `start` (aware) for `days`. Pass shifts/holidays/staffing to avoid DB access (tests)."""
    days = days or int(config.get("aps.horizon_days", 14))
    slot_minutes = slot_minutes or int(config.get("aps.slot_minutes", 5))
    if shifts is None or working_days is None:
        s, w = shift_settings()
        shifts = s if shifts is None else shifts
        working_days = w if working_days is None else working_days
    start = start.astimezone(tz())
    start = start.replace(second=0, microsecond=0)
    start -= timedelta(minutes=start.minute % slot_minutes)
    end = start + timedelta(days=days)
    if holidays is None:
        holidays = holidays_between(start.date(), end.date())
    if staffing is None:
        staffing = staffing_between(start.date(), end.date())
    prof = minute_profile(shifts)
    slots = []
    t = start
    while t < end:
        d = t.date()
        info = prof.get(t.hour * 60 + t.minute) if (t.weekday() in working_days and d not in holidays) else None
        if info:
            code, workers = info
            slots.append(Slot(t, True, code, staffing.get((d, code), workers)))
        else:
            slots.append(Slot(t, False))
        t += timedelta(minutes=slot_minutes)
    return slots


def planned_minutes(d0, d1):
    """Working (planned production) minutes per day between two dates, inclusive, for OEE."""
    shifts, working_days = shift_settings()
    prof = minute_profile(shifts)
    hol = holidays_between(d0, d1)
    total = 0
    d = d0
    while d <= d1:
        if d.weekday() in working_days and d not in hol:
            total += len(prof)
        d += timedelta(days=1)
    return total


def day_end(d, tzinfo=None):
    return datetime.combine(d, time(23, 59, 59), tzinfo=tzinfo or tz())


def parse_date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
