"""
Workstation list, built from settings (workstations.count) and the industry
routing. Workstation n runs routing step n; if there are more workstations
than steps, the extra ones repeat the last step (e.g. a second QC bench).
"""
from core import config


def routing(industry_code=None):
    steps = config.industry(industry_code)["steps"]
    return [{**s, "step_no": i} for i, s in enumerate(steps, start=1)]


def list_workstations():
    steps = routing()
    count = int(config.get("workstations.count", len(steps)))
    prefix = config.get("workstations.code_prefix", "WS")
    out = []
    for n in range(1, count + 1):
        step = steps[min(n, len(steps)) - 1]
        out.append({"code": f"{prefix}-{n:02d}", "step_no": step["step_no"], "step_code": step["code"],
                    "step_name": step["name"], "measurement": step.get("measurement"),
                    "is_qc": bool(step.get("is_qc"))})
    return out


def get_workstation(code):
    for ws in list_workstations():
        if ws["code"] == code:
            return ws
    return None
