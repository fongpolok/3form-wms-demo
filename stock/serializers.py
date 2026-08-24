from rest_framework import serializers
from .models import StockListModel, StockBinModel
from utils import datasolve

class StockListGetSerializer(serializers.ModelSerializer):
    goods_code = serializers.CharField(read_only=True, required=False)
    goods_desc = serializers.CharField(read_only=True, required=False)
    goods_qty = serializers.IntegerField(read_only=True, required=False)
    onhand_stock = serializers.IntegerField(read_only=True, required=False)
    can_order_stock = serializers.IntegerField(read_only=True, required=False)
    inspect_stock = serializers.IntegerField(read_only=True, required=False)
    hold_stock = serializers.IntegerField(read_only=True, required=False)
    damage_stock = serializers.IntegerField(read_only=True, required=False)
    asn_stock = serializers.IntegerField(read_only=True, required=False)
    dn_stock = serializers.IntegerField(read_only=True, required=False)
    pre_load_stock = serializers.IntegerField(read_only=True, required=False)
    pre_sort_stock = serializers.IntegerField(read_only=True, required=False)
    sorted_stock = serializers.IntegerField(read_only=True, required=False)
    pick_stock = serializers.IntegerField(read_only=True, required=False)
    picked_stock = serializers.IntegerField(read_only=True, required=False)
    back_order_stock = serializers.IntegerField(read_only=True, required=False)
    lot_number = serializers.CharField(read_only=True, required=False)
    wip_id = serializers.CharField(read_only=True, required=False)
    expiry_date = serializers.DateField(read_only=True, required=False)
    wip_status = serializers.IntegerField(read_only=True, required=False)
    is_void = serializers.BooleanField(read_only=True, required=False)
    void_reason = serializers.CharField(read_only=True, required=False)
    void_time = serializers.DateTimeField(read_only=True, required=False, format='%Y-%m-%d %H:%M:%S')
    source_asn_code = serializers.CharField(read_only=True, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = StockListModel
        exclude = ['openid']
        read_only_fields = ['id']

class StockLotRecordSerializer(serializers.Serializer):
    """Input for stock/services.record_lot - tags untracked on-hand stock
    into a lot with a lot number + expiry date."""
    goods_code = serializers.CharField(required=True, validators=[datasolve.data_validate])
    lot_number = serializers.CharField(required=True, validators=[datasolve.data_validate])
    expiry_date = serializers.DateField(required=False, allow_null=True)
    qty = serializers.IntegerField(required=True, validators=[datasolve.qty_0_data_validate])
    creater = serializers.CharField(required=True, validators=[datasolve.data_validate])
    source_asn_code = serializers.CharField(required=False, allow_blank=True, default="")

class StockVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, validators=[datasolve.data_validate])

class StockBinGetSerializer(serializers.ModelSerializer):
    bin_name = serializers.CharField(read_only=True, required=False)
    goods_code = serializers.CharField(read_only=True, required=False)
    goods_desc = serializers.CharField(read_only=True, required=False)
    goods_qty = serializers.IntegerField(read_only=True, required=False)
    pick_qty = serializers.IntegerField(read_only=True, required=False)
    picked_qty = serializers.IntegerField(read_only=True, required=False)
    bin_size = serializers.CharField(read_only=True, required=False)
    bin_property = serializers.CharField(read_only=True, required=False)
    qty = serializers.SerializerMethodField()
    t_code = serializers.CharField(read_only=True, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = StockBinModel
        exclude = ['openid', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

    def get_qty(self, obj):
        return 0

class StockBinPostSerializer(serializers.ModelSerializer):
    openid = serializers.CharField(read_only=False, required=False, validators=[datasolve.openid_validate])
    bin_name = serializers.CharField(read_only=True, required=False, validators=[datasolve.data_validate])
    move_to_bin = serializers.CharField(read_only=True, required=False, validators=[datasolve.data_validate])
    move_qty = serializers.CharField(read_only=True, required=False, validators=[datasolve.data_validate])

    class Meta:
        model = StockBinModel
        exclude = []
        read_only_fields = ['id', 'openid', 'create_time', 'update_time', ]

class FileBinListRenderSerializer(serializers.ModelSerializer):
    bin_name = serializers.CharField(read_only=False, required=False)
    goods_code = serializers.CharField(read_only=False, required=False)
    goods_desc = serializers.CharField(read_only=False, required=False)
    goods_qty = serializers.IntegerField(read_only=False, required=False)
    pick_qty = serializers.IntegerField(read_only=False, required=False)
    picked_qty = serializers.IntegerField(read_only=False, required=False)
    bin_size = serializers.CharField(read_only=False, required=False)
    bin_property = serializers.CharField(read_only=False, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = StockBinModel
        ref_name = 'StockFileBinListRenderSerializer'
        exclude = ['openid', ]

class FileListRenderSerializer(serializers.ModelSerializer):
    goods_code = serializers.CharField(read_only=True, required=False)
    goods_desc = serializers.CharField(read_only=True, required=False)
    goods_qty = serializers.IntegerField(read_only=True, required=False)
    onhand_stock = serializers.IntegerField(read_only=True, required=False)
    can_order_stock = serializers.IntegerField(read_only=True, required=False)
    inspect_stock = serializers.IntegerField(read_only=True, required=False)
    hold_stock = serializers.IntegerField(read_only=True, required=False)
    damage_stock = serializers.IntegerField(read_only=True, required=False)
    asn_stock = serializers.IntegerField(read_only=True, required=False)
    dn_stock = serializers.IntegerField(read_only=True, required=False)
    pre_load_stock = serializers.IntegerField(read_only=True, required=False)
    pre_sort_stock = serializers.IntegerField(read_only=True, required=False)
    sorted_stock = serializers.IntegerField(read_only=True, required=False)
    pick_stock = serializers.IntegerField(read_only=True, required=False)
    picked_stock = serializers.IntegerField(read_only=True, required=False)
    back_order_stock = serializers.IntegerField(read_only=True, required=False)
    lot_number = serializers.CharField(read_only=True, required=False)
    wip_id = serializers.CharField(read_only=True, required=False)
    expiry_date = serializers.DateField(read_only=True, required=False)
    wip_status = serializers.IntegerField(read_only=True, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = StockListModel
        ref_name = 'StockFileListRenderSerializer'
        exclude = ['openid', ]
