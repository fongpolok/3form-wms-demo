from django.db import models
from .constants import WIP_STATUS_CHOICES, WIP_STATUS_RECEIVED

class StockListModel(models.Model):
    goods_code = models.CharField(max_length=255, verbose_name="Goods Code")
    goods_desc = models.CharField(max_length=255, verbose_name="Goods Description")
    goods_qty = models.BigIntegerField(default=0, verbose_name="Total Qty")
    onhand_stock = models.BigIntegerField(default=0, verbose_name='On Hand Stock')
    can_order_stock = models.BigIntegerField(default=0, verbose_name='Can Order Stock')
    ordered_stock = models.BigIntegerField(default=0, verbose_name='Ordered Stock')
    inspect_stock = models.BigIntegerField(default=0, verbose_name='Inspect Stock')
    hold_stock = models.BigIntegerField(default=0, verbose_name='Holding Stock')
    damage_stock = models.BigIntegerField(default=0, verbose_name='Damage Stock')
    asn_stock = models.BigIntegerField(default=0, verbose_name='ASN Stock')
    dn_stock = models.BigIntegerField(default=0, verbose_name='DN Stock')
    pre_load_stock = models.BigIntegerField(default=0, verbose_name='Pre Load Stock')
    pre_sort_stock = models.BigIntegerField(default=0, verbose_name='Pre Sort Stock')
    sorted_stock = models.BigIntegerField(default=0, verbose_name='Sorted Stock')
    pick_stock = models.BigIntegerField(default=0, verbose_name='Pick Stock')
    picked_stock = models.BigIntegerField(default=0, verbose_name='Picked Stock')
    back_order_stock = models.BigIntegerField(default=0, verbose_name='Back Order Stock')
    supplier = models.CharField(default='', max_length=255, verbose_name='Goods Supplier')
    openid = models.CharField(max_length=255, verbose_name="Openid")
    # --- Lot / FEFO / WIP tracking (medical device traceability) ---
    lot_number = models.CharField(default='', blank=True, max_length=255, verbose_name="Lot Number")
    wip_id = models.CharField(max_length=64, unique=True, null=True, blank=True, verbose_name="WIP Unique ID")
    expiry_date = models.DateField(null=True, blank=True, verbose_name="Expiry Date")
    wip_status = models.IntegerField(default=WIP_STATUS_RECEIVED, choices=WIP_STATUS_CHOICES, verbose_name="WIP Status")
    is_void = models.BooleanField(default=False, verbose_name="Void Label")
    void_reason = models.CharField(default='', blank=True, max_length=255, verbose_name="Void Reason")
    void_time = models.DateTimeField(null=True, blank=True, verbose_name="Void Time")
    source_asn_code = models.CharField(default='', blank=True, max_length=255, verbose_name="Source ASN Code")
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="Create Time")
    update_time = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="Update Time")

    class Meta:
        db_table = 'stocklist'
        verbose_name = 'Stock List'
        verbose_name_plural = "Stock List"
        ordering = ['-id']

class StockBinModel(models.Model):
    bin_name = models.CharField(max_length=255, verbose_name="Bin Name")
    goods_code = models.CharField(max_length=255, verbose_name="Goods Code")
    goods_desc = models.CharField(max_length=255, verbose_name="Goods Description")
    goods_qty = models.BigIntegerField(default=0, verbose_name="Binstock Qty")
    pick_qty = models.BigIntegerField(default=0, verbose_name="BinPick Qty")
    picked_qty = models.BigIntegerField(default=0, verbose_name="BinPicked Qty")
    bin_size = models.CharField(max_length=255, verbose_name="Bin size")
    bin_property = models.CharField(max_length=255, verbose_name="Bin Property")
    t_code = models.CharField(max_length=255, verbose_name="Transaction Code")
    openid = models.CharField(max_length=255, verbose_name="Openid")
    create_time = models.DateTimeField(auto_now_add=False, verbose_name="Create Time")
    update_time = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="Update Time")

    class Meta:
        db_table = 'stockbin'
        verbose_name = 'Stock Bin'
        verbose_name_plural = "Stock Bin"
        ordering = ['-id']
