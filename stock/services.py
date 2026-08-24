"""
Business logic for lot/FEFO tracking and low-stock/expiry alerts.

Kept out of views.py on purpose: these are plain functions (no request/response
handling) so they can be reused from an API view, a management command, or a
test, and so the alert thresholds in WMS_ALERT_SETTINGS stay the only thing
you need to tune.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from utils.md5 import Md5
from goods.models import ListModel as GoodsModel
from .constants import WIP_STATUS_RECEIVED
from .models import StockListModel

logger = logging.getLogger("stock")


def _alert_settings():
    return getattr(settings, "WMS_ALERT_SETTINGS", {})


def get_low_stock_alerts(openid):
    """Goods whose total on-hand quantity (summed across all lots) is at or
    below the product's safety_stock. Returns a list of dicts."""
    if not _alert_settings().get("LOW_STOCK_ALERT_ENABLED", True):
        return []

    onhand_by_goods = (
        StockListModel.objects
        .filter(openid=openid, is_void=False)
        .values("goods_code", "goods_desc")
        .annotate(total_onhand=Sum("onhand_stock"))
    )
    safety_stock_by_code = {
        g.goods_code: g.safety_stock
        for g in GoodsModel.objects.filter(openid=openid, is_delete=False)
    }

    alerts = []
    for row in onhand_by_goods:
        safety_stock = safety_stock_by_code.get(row["goods_code"])
        if safety_stock is None or safety_stock <= 0:
            continue
        onhand = row["total_onhand"] or 0
        if onhand <= safety_stock:
            alerts.append({
                "goods_code": row["goods_code"],
                "goods_desc": row["goods_desc"],
                "onhand_stock": onhand,
                "safety_stock": safety_stock,
            })
            logger.warning(
                "Low stock alert: goods_code=%s onhand=%s safety_stock=%s openid=%s",
                row["goods_code"], onhand, safety_stock, openid,
            )
    return alerts


def get_expiry_alerts(openid, days=None):
    """Lots expiring within `days` (default WMS_ALERT_SETTINGS['EXPIRY_ALERT_DAYS'])
    that still have stock on hand and haven't been voided."""
    if not _alert_settings().get("EXPIRY_ALERT_ENABLED", True):
        return []
    if days is None:
        days = _alert_settings().get("EXPIRY_ALERT_DAYS", 90)

    cutoff = timezone.now().date() + timedelta(days=days)
    lots = StockListModel.objects.filter(
        openid=openid,
        is_void=False,
        onhand_stock__gt=0,
        expiry_date__isnull=False,
        expiry_date__lte=cutoff,
    ).order_by("expiry_date")

    alerts = []
    today = timezone.now().date()
    for lot in lots:
        days_left = (lot.expiry_date - today).days
        alerts.append({
            "id": lot.id,
            "wip_id": lot.wip_id,
            "goods_code": lot.goods_code,
            "goods_desc": lot.goods_desc,
            "lot_number": lot.lot_number,
            "expiry_date": lot.expiry_date.isoformat(),
            "days_left": days_left,
            "onhand_stock": lot.onhand_stock,
        })
        logger.warning(
            "Expiry alert: goods_code=%s lot_number=%s expiry_date=%s days_left=%s openid=%s",
            lot.goods_code, lot.lot_number, lot.expiry_date, days_left, openid,
        )
    return alerts


def get_fefo_pick_order(openid, goods_code):
    """Advisory pick order for a goods_code: earliest expiry first (FEFO),
    lots with no expiry_date fall back to earliest-received first (FIFO).
    Phase 1 is advisory only - this does not reserve or move any stock."""
    # Query in two parts instead of relying on DB-specific NULLS LAST syntax,
    # to stay portable between SQLite (dev) and Postgres (prod).
    with_expiry = list(
        StockListModel.objects.filter(
            openid=openid, goods_code=goods_code, is_void=False,
            onhand_stock__gt=0, expiry_date__isnull=False,
        ).order_by("expiry_date", "create_time")
    )
    without_expiry = list(
        StockListModel.objects.filter(
            openid=openid, goods_code=goods_code, is_void=False,
            onhand_stock__gt=0, expiry_date__isnull=True,
        ).order_by("create_time")
    )
    logger.info(
        "FEFO pick order computed: goods_code=%s openid=%s lots_with_expiry=%s lots_without_expiry=%s",
        goods_code, openid, len(with_expiry), len(without_expiry),
    )
    return with_expiry + without_expiry


def record_lot(openid, goods_code, lot_number, expiry_date, qty, creater, source_asn_code=""):
    """Tag `qty` units of untracked on-hand stock (the plain, lot-less
    StockListModel row created by normal ASN receiving) into a tracked lot.

    This is a pure re-classification, not a new receipt: it moves quantity
    from the untracked bucket into a lot-tracked bucket so the total on-hand
    count never changes. Mirrors the existing bin "move" pattern already used
    in stock/views.py (decrement source, increment/create destination).
    """
    from rest_framework.exceptions import APIException

    untracked = StockListModel.objects.filter(
        openid=openid, goods_code=goods_code, lot_number=""
    ).first()
    if untracked is None or untracked.onhand_stock < qty:
        available = untracked.onhand_stock if untracked else 0
        logger.error(
            "record_lot rejected: not enough untracked stock. goods_code=%s requested=%s available=%s openid=%s",
            goods_code, qty, available, openid,
        )
        raise APIException({"detail": "Not enough untracked on-hand stock to record this lot"})

    untracked.onhand_stock -= qty
    untracked.goods_qty -= qty
    untracked.save()

    lot = StockListModel.objects.filter(
        openid=openid, goods_code=goods_code, lot_number=lot_number, is_void=False
    ).first()
    if lot is not None:
        lot.onhand_stock += qty
        lot.goods_qty += qty
        lot.save()
        logger.info(
            "record_lot: added qty=%s to existing lot wip_id=%s goods_code=%s lot_number=%s openid=%s",
            qty, lot.wip_id, goods_code, lot_number, openid,
        )
        return lot

    goods = GoodsModel.objects.filter(openid=openid, goods_code=goods_code, is_delete=False).first()
    lot = StockListModel.objects.create(
        openid=openid,
        goods_code=goods_code,
        goods_desc=goods.goods_desc if goods else untracked.goods_desc,
        goods_qty=qty,
        onhand_stock=qty,
        supplier=goods.goods_supplier if goods else "",
        lot_number=lot_number,
        wip_id="WIP" + Md5.md5(goods_code + lot_number + str(timezone.now())),
        expiry_date=expiry_date,
        wip_status=WIP_STATUS_RECEIVED,
        source_asn_code=source_asn_code,
    )
    logger.info(
        "record_lot: created new lot wip_id=%s goods_code=%s lot_number=%s qty=%s expiry_date=%s openid=%s creater=%s",
        lot.wip_id, goods_code, lot_number, qty, expiry_date, openid, creater,
    )
    return lot


def void_lot(lot, reason):
    """Soft-void a lot: never delete (needed for recall/audit traceability).
    Rejected if any of it has already been picked or shipped."""
    from rest_framework.exceptions import APIException

    if lot.picked_stock > 0 or lot.dn_stock > 0:
        logger.error(
            "void_lot rejected: lot already picked/shipped. wip_id=%s picked_stock=%s dn_stock=%s",
            lot.wip_id, lot.picked_stock, lot.dn_stock,
        )
        raise APIException({"detail": "Cannot void a lot that has already been picked or shipped"})

    lot.is_void = True
    lot.void_reason = reason
    lot.void_time = timezone.now()
    lot.save()
    logger.warning("Lot voided: wip_id=%s goods_code=%s lot_number=%s reason=%s", lot.wip_id, lot.goods_code, lot.lot_number, reason)
    return lot
