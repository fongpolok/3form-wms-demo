<template>
  <div>
    <transition appear enter-active-class="animated fadeIn">
      <q-table
        class="my-sticky-header-table shadow-24"
        :data="table_list"
        row-key="id"
        :separator="separator"
        :loading="loading"
        :filter="filter"
        :columns="columns"
        hide-bottom
        :pagination.sync="pagination"
        no-data-label="No data"
        no-results-label="No data you want"
        :table-style="{ height: height }"
        flat
        bordered
      >
        <template v-slot:top>
          <q-btn-group push>
            <q-btn :label="$t('refresh')" icon="refresh" @click="reFresh()">
              <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]" content-style="font-size: 12px">{{ $t('refreshtip') }}</q-tooltip>
            </q-btn>
            <q-btn :label="$t('stock.view_stocklist.record_lot')" icon="add_box" color="primary" @click="openRecordLot()" />
          </q-btn-group>
          <q-space />
          <q-input outlined rounded dense debounce="300" color="primary" v-model="filter" :placeholder="$t('search')" @input="getSearchList()" @keyup.enter="getSearchList()">
            <template v-slot:append>
              <q-icon name="search" @click="getSearchList()" />
            </template>
          </q-input>
        </template>
        <template v-slot:body="props">
          <q-tr :props="props">
            <q-td key="goods_code" :props="props">{{ props.row.goods_code }}</q-td>
            <q-td key="goods_desc" :props="props">{{ props.row.goods_desc }}</q-td>
            <q-td key="goods_qty" :props="props">{{ props.row.goods_qty }}</q-td>
            <q-td key="onhand_stock" :props="props">{{ props.row.onhand_stock }}</q-td>
            <q-td key="can_order_stock" :props="props">{{ props.row.can_order_stock }}</q-td>
            <q-td key="ordered_stock" :props="props">{{ props.row.ordered_stock }}</q-td>
            <q-td key="inspect_stock" :props="props">{{ props.row.inspect_stock }}</q-td>
            <q-td key="hold_stock" :props="props">{{ props.row.hold_stock }}</q-td>
            <q-td key="damage_stock" :props="props">{{ props.row.damage_stock }}</q-td>
            <q-td key="asn_stock" :props="props">{{ props.row.asn_stock }}</q-td>
            <q-td key="dn_stock" :props="props">{{ props.row.dn_stock }}</q-td>
            <q-td key="pre_load_stock" :props="props">{{ props.row.pre_load_stock }}</q-td>
            <q-td key="pre_sort_stock" :props="props">{{ props.row.pre_sort_stock }}</q-td>
            <q-td key="sorted_stock" :props="props">{{ props.row.sorted_stock }}</q-td>
            <q-td key="pick_stock" :props="props">{{ props.row.pick_stock }}</q-td>
            <q-td key="picked_stock" :props="props">{{ props.row.picked_stock }}</q-td>
            <q-td key="back_order_stock" :props="props">{{ props.row.back_order_stock }}</q-td>
            <q-td key="lot_number" :props="props">{{ props.row.lot_number }}</q-td>
            <q-td key="expiry_date" :props="props">{{ props.row.expiry_date }}</q-td>
            <q-td key="wip_status" :props="props">
              <q-chip v-if="props.row.lot_number" dense square :color="wipStatusColor(props.row)" text-color="white">
                {{ wipStatusLabel(props.row.wip_status) }}
              </q-chip>
            </q-td>
            <q-td key="create_time" :props="props">{{ props.row.create_time }}</q-td>
            <q-td key="update_time" :props="props">{{ props.row.update_time }}</q-td>
            <q-td key="action" :props="props">
              <q-btn
                v-if="props.row.lot_number && !props.row.is_void"
                dense
                flat
                round
                color="negative"
                icon="block"
                @click="openVoid(props.row)"
              >
                <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]" content-style="font-size: 12px">{{ $t('stock.view_stocklist.void_lot') }}</q-tooltip>
              </q-btn>
            </q-td>
          </q-tr>
        </template>
      </q-table>
    </transition>
    <q-dialog v-model="recordLotForm">
      <q-card style="min-width: 400px">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ $t('stock.view_stocklist.record_lot') }}</div>
          <q-space></q-space>
          <q-btn dense flat icon="close" v-close-popup />
        </q-bar>
        <q-card-section class="q-pt-md">
          <q-input dense outlined square v-model="recordLotData.goods_code" :label="$t('stock.view_stocklist.goods_code')" @keyup.enter="submitRecordLot()" />
          <q-input dense outlined square v-model="recordLotData.lot_number" :label="$t('stock.view_stocklist.lot_number')" style="margin-top: 5px" @keyup.enter="submitRecordLot()" />
          <q-input dense outlined square v-model.number="recordLotData.qty" type="number" :label="$t('stock.view_stocklist.qty')" style="margin-top: 5px" @keyup.enter="submitRecordLot()" />
          <q-input dense outlined square readonly v-model="recordLotData.expiry_date" :label="$t('stock.view_stocklist.expiry_date')" style="margin-top: 5px">
            <template v-slot:append>
              <q-icon name="event" class="cursor-pointer">
                <q-popup-proxy transition-show="scale" transition-hide="scale">
                  <q-date v-model="recordLotData.expiry_date" mask="YYYY-MM-DD">
                    <div class="row items-center justify-end">
                      <q-btn v-close-popup :label="$t('index.close')" color="primary" flat />
                    </div>
                  </q-date>
                </q-popup-proxy>
              </q-icon>
            </template>
          </q-input>
        </q-card-section>
        <q-card-actions align="right" class="q-mx-sm">
          <q-btn class="full-width" color="primary" :label="$t('submit')" @click="submitRecordLot()" />
        </q-card-actions>
      </q-card>
    </q-dialog>
    <q-dialog v-model="voidForm">
      <q-card style="min-width: 350px">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ $t('stock.view_stocklist.void_lot') }}</div>
          <q-space></q-space>
          <q-btn dense flat icon="close" v-close-popup />
        </q-bar>
        <q-card-section class="q-pt-md">
          <q-input dense outlined square v-model="voidReason" :label="$t('stock.view_stocklist.void_reason')" @keyup.enter="submitVoid()" />
        </q-card-section>
        <q-card-actions align="right" class="q-mx-sm">
          <q-btn class="full-width" color="negative" :label="$t('stock.view_stocklist.void_lot')" @click="submitVoid()" />
        </q-card-actions>
      </q-card>
    </q-dialog>
    <template>
        <div v-show="max !== 0" class="q-pa-lg flex flex-center">
           <div>{{ total }} </div>
          <q-pagination
            v-model="current"
            color="black"
            :max="max"
            :max-pages="6"
            boundary-links
            @click="getList()"
          />
          <div>
            <input
              v-model="paginationIpt"
              @blur="changePageEnter"
              @keyup.enter="changePageEnter"
              style="width: 60px; text-align: center"
            />
          </div>
        </div>
        <div v-show="max === 0" class="q-pa-lg flex flex-center">
          <q-btn flat push color="dark" :label="$t('no_data')"></q-btn>
        </div>
    </template>
  </div>
</template>
<router-view />

<script>
import { getauth, getfile, postauth, patchauth } from 'boot/axios_request';
import { date, exportFile, LocalStorage } from 'quasar';

export default {
  name: 'Pagestocklist',
  data() {
    return {
      openid: '',
      login_name: '',
      authin: '0',
      pathname: 'stock/list/',
      pathname_previous: '',
      pathname_next: '',
      separator: 'cell',
      loading: false,
      height: '',
      table_list: [],
      bin_size_list: [],
      bin_property_list: [],
      warehouse_list: [],
      columns: [
        { name: 'goods_code', required: true, label: this.$t('stock.view_stocklist.goods_code'), align: 'left', field: 'goods_code' },
        { name: 'goods_desc', label: this.$t('stock.view_stocklist.goods_desc'), field: 'goods_desc', align: 'center' },
        { name: 'goods_qty', label: this.$t('stock.view_stocklist.goods_qty'), field: 'goods_qty', align: 'center' },
        { name: 'onhand_stock', label: this.$t('stock.view_stocklist.onhand_stock'), field: 'onhand_stock', align: 'center' },
        { name: 'can_order_stock', label: this.$t('stock.view_stocklist.can_order_stock'), field: 'can_order_stock', align: 'center' },
        { name: 'ordered_stock', label: this.$t('stock.view_stocklist.ordered_stock'), field: 'ordered_stock', align: 'center' },
        { name: 'inspect_stock', label: this.$t('stock.view_stocklist.inspect_stock'), field: 'inspect_stock', align: 'center' },
        { name: 'hold_stock', label: this.$t('stock.view_stocklist.hold_stock'), field: 'hold_stock', align: 'center' },
        { name: 'damage_stock', label: this.$t('stock.view_stocklist.damage_stock'), field: 'damage_stock', align: 'center' },
        { name: 'asn_stock', label: this.$t('stock.view_stocklist.asn_stock'), field: 'asn_stock', align: 'center' },
        { name: 'dn_stock', label: this.$t('stock.view_stocklist.dn_stock'), field: 'dn_stock', align: 'center' },
        { name: 'pre_load_stock', label: this.$t('stock.view_stocklist.pre_load_stock'), field: 'pre_load_stock', align: 'center' },
        { name: 'pre_sort_stock', label: this.$t('stock.view_stocklist.pre_sort_stock'), field: 'pre_sort_stock', align: 'center' },
        { name: 'sorted_stock', label: this.$t('stock.view_stocklist.sorted_stock'), field: 'sorted_stock', align: 'center' },
        { name: 'pick_stock', label: this.$t('stock.view_stocklist.pick_stock'), field: 'pick_stock', align: 'center' },
        { name: 'picked_stock', label: this.$t('stock.view_stocklist.picked_stock'), field: 'picked_stock', align: 'center' },
        { name: 'back_order_stock', label: this.$t('stock.view_stocklist.back_order_stock'), field: 'back_order_stock', align: 'center' },
        { name: 'lot_number', label: this.$t('stock.view_stocklist.lot_number'), field: 'lot_number', align: 'center' },
        { name: 'expiry_date', label: this.$t('stock.view_stocklist.expiry_date'), field: 'expiry_date', align: 'center' },
        { name: 'wip_status', label: this.$t('stock.view_stocklist.wip_status'), field: 'wip_status', align: 'center' },
        { name: 'create_time', label: this.$t('createtime'), field: 'create_time', align: 'center' },
        { name: 'update_time', label: this.$t('updatetime'), field: 'update_time', align: 'center' },
        { name: 'action', label: this.$t('action'), field: 'action', align: 'center' }
      ],
      filter: '',
      pagination: {
        page: 1,
        rowsPerPage: '30'
      },
      current: 1,
      max: 0,
      total: 0,
      paginationIpt: 1,
      recordLotForm: false,
      recordLotData: {
        goods_code: '',
        lot_number: '',
        qty: null,
        expiry_date: ''
      },
      voidForm: false,
      voidReason: '',
      voidTargetId: null,
      // Matches stock/constants.py WIP_STATUS_CHOICES - kept in sync with the backend.
      wipStatusLabels: {
        10: this.$t('stock.view_stocklist.wip_received'),
        20: this.$t('stock.view_stocklist.wip_inspected'),
        30: this.$t('stock.view_stocklist.wip_putaway'),
        40: this.$t('stock.view_stocklist.wip_picking'),
        50: this.$t('stock.view_stocklist.wip_picked'),
        60: this.$t('stock.view_stocklist.wip_delivered'),
        70: this.$t('stock.view_stocklist.wip_used'),
        90: this.$t('stock.view_stocklist.wip_void')
      }
    };
  },
  methods: {
    wipStatusLabel(code) {
      return this.wipStatusLabels[code] || code;
    },
    wipStatusColor(row) {
      if (row.is_void) {
        return 'grey';
      }
      if (row.wip_status >= 60) {
        return 'positive';
      }
      if (row.wip_status >= 40) {
        return 'warning';
      }
      return 'primary';
    },
    openRecordLot() {
      this.recordLotData = { goods_code: '', lot_number: '', qty: null, expiry_date: '' };
      this.recordLotForm = true;
    },
    submitRecordLot() {
      var _this = this;
      if (!_this.recordLotData.goods_code || !_this.recordLotData.lot_number || !_this.recordLotData.qty) {
        _this.$q.notify({ message: 'Please fill in Goods Code, Lot Number and Qty', icon: 'close', color: 'negative' });
        return;
      }
      postauth('stock/recordlot/', {
        goods_code: _this.recordLotData.goods_code,
        lot_number: _this.recordLotData.lot_number,
        expiry_date: _this.recordLotData.expiry_date || null,
        qty: _this.recordLotData.qty,
        creater: _this.login_name
      })
        .then(res => {
          _this.recordLotForm = false;
          _this.$q.notify({ message: 'Lot Recorded', icon: 'check', color: 'green' });
          _this.getList();
        })
        .catch(err => {
          _this.$q.notify({ message: err.detail, icon: 'close', color: 'negative' });
        });
    },
    openVoid(row) {
      this.voidTargetId = row.id;
      this.voidReason = '';
      this.voidForm = true;
    },
    submitVoid() {
      var _this = this;
      if (!_this.voidReason) {
        _this.$q.notify({ message: 'Please enter a reason', icon: 'close', color: 'negative' });
        return;
      }
      patchauth('stock/' + _this.voidTargetId + '/void/', { reason: _this.voidReason })
        .then(res => {
          _this.voidForm = false;
          _this.$q.notify({ message: 'Lot Voided', icon: 'check', color: 'green' });
          _this.getList();
        })
        .catch(err => {
          _this.$q.notify({ message: err.detail, icon: 'close', color: 'negative' });
        });
    },
    getList() {
      var _this = this;
      getauth(_this.pathname + '?ordering=-update_time' + '&page=' + '' + _this.current, {})
        .then(res => {
          _this.table_list = res.results;
          _this.total = res.count
          if (res.count === 0) {
            _this.max = 0
          } else {
            if (Math.ceil(res.count / 30) === 1) {
              _this.max = 0
            } else {
              _this.max = Math.ceil(res.count / 30)
            }
          }
          _this.pathname_previous = res.previous;
          _this.pathname_next = res.next;
        })
        .catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          });
        });
    },
    changePageEnter(e) {
      if (Number(this.paginationIpt) < 1) {
        this.current = 1;
        this.paginationIpt = 1;
      } else if (Number(this.paginationIpt) > this.max) {
        this.current = this.max;
        this.paginationIpt = this.max;
      } else {
        this.current = Number(this.paginationIpt);
      }
      this.getList();
    },
    getSearchList() {
      var _this = this;
      if (LocalStorage.has('auth')) {
        _this.current = 1
        _this.paginationIpt = 1
        getauth(_this.pathname + '?ordering=-update_time' + '&goods_code__icontains=' + _this.filter + '&page=' + '' + _this.current, {})
          .then(res => {
            _this.table_list = res.results;
            _this.total = res.count
            if (res.count === 0) {
              _this.max = 0
            } else {
              if (Math.ceil(res.count / 30) === 1) {
                _this.max = 0
              } else {
                _this.max = Math.ceil(res.count / 30)
              }
            }
            _this.pathname_previous = res.previous;
            _this.pathname_next = res.next;
          })
          .catch(err => {
            _this.$q.notify({
              message: err.detail,
              icon: 'close',
              color: 'negative'
            });
          });
      } else {
      }
    },
    getListPrevious() {
      var _this = this;
      if (LocalStorage.has('auth')) {
        getauth(_this.pathname_previous, {})
          .then(res => {
            _this.table_list = res.results;
            _this.pathname_previous = res.previous;
            _this.pathname_next = res.next;
          })
          .catch(err => {
            _this.$q.notify({
              message: err.detail,
              icon: 'close',
              color: 'negative'
            });
          });
      } else {
      }
    },
    getListNext() {
      var _this = this;
      if (LocalStorage.has('auth')) {
        getauth(_this.pathname_next, {})
          .then(res => {
            _this.table_list = res.results;
            _this.pathname_previous = res.previous;
            _this.pathname_next = res.next;
          })
          .catch(err => {
            _this.$q.notify({
              message: err.detail,
              icon: 'close',
              color: 'negative'
            });
          });
      } else {
      }
    },
    reFresh() {
      var _this = this;
      _this.getList();
    }
  },
  created() {
    var _this = this;
    if (LocalStorage.has('openid')) {
      _this.openid = LocalStorage.getItem('openid');
    } else {
      _this.openid = '';
      LocalStorage.set('openid', '');
    }
    if (LocalStorage.has('login_name')) {
      _this.login_name = LocalStorage.getItem('login_name');
    } else {
      _this.login_name = '';
      LocalStorage.set('login_name', '');
    }
    if (LocalStorage.has('auth')) {
      _this.authin = '1';
      _this.getList();
    } else {
      _this.authin = '0';
    }
  },
  mounted() {
    var _this = this;
    if (_this.$q.platform.is.electron) {
      _this.height = String(_this.$q.screen.height - 290) + 'px';
    } else {
      _this.height = _this.$q.screen.height - 290 + '' + 'px';
    }
  },
  updated() {},
  destroyed() {}
};
</script>
