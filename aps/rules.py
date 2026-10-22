"""Planning rules the PIC may change on the Calendar page (stored as site settings);
everything else comes from settings.yaml -> aps."""
from core import config

# name -> (lowest, highest) allowed value
EDITABLE = {"changeover_cost_minutes": (0, 600), "group_same_product_days": (0, 14)}


def get(name):
    from inventory.site import get_setting
    value = get_setting(f"aps.{name}") if name in EDITABLE else None
    return config.get(f"aps.{name}") if value is None else value


def editable():
    return {name: get(name) for name in EDITABLE}


def validate(data):
    """Returns {name: number} for the editable rules found in `data`, or raises ValueError."""
    out = {}
    for name, (lo, hi) in EDITABLE.items():
        if name in data:
            try:
                v = float(data[name])
            except (TypeError, ValueError):
                raise ValueError(f"{name} must be a number.")
            if not lo <= v <= hi:
                raise ValueError(f"{name} must be between {lo} and {hi}.")
            out[name] = int(v) if v == int(v) else v
    return out
