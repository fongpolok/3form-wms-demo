"""
Tunable constants for lot/WIP tracking (medical-device FEFO feature).

Kept in one place, rather than scattered across views/serializers, so the
8-stage WIP flow can be read or adjusted without touching business logic.
"""

WIP_STATUS_RECEIVED = 10
WIP_STATUS_INSPECTED = 20
WIP_STATUS_PUTAWAY = 30
WIP_STATUS_PICKING = 40
WIP_STATUS_PICKED = 50
WIP_STATUS_DELIVERED = 60
WIP_STATUS_USED = 70
WIP_STATUS_VOID = 90

WIP_STATUS_CHOICES = (
    (WIP_STATUS_RECEIVED, 'Received'),
    (WIP_STATUS_INSPECTED, 'Inspected'),
    (WIP_STATUS_PUTAWAY, 'Put Away'),
    (WIP_STATUS_PICKING, 'Picking'),
    (WIP_STATUS_PICKED, 'Picked'),
    (WIP_STATUS_DELIVERED, 'Delivered'),
    (WIP_STATUS_USED, 'Used'),
    (WIP_STATUS_VOID, 'Void'),
)

WIP_STATUS_LABELS = dict(WIP_STATUS_CHOICES)
