<script setup>
// Stock from the new ledger: on hand, reserved for orders, available; lots with
// bin + expiry; open material requests (shortages) with a Re-check button.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, post } from '../../api/client.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'

const { t } = useI18n()
const stock = usePolled(() => get('/api/v1/inventory/stock'), 20000)
const requests = usePolled(() => get('/api/v1/inventory/material-requests'), 20000)
const open = ref({})
const q = ref('')
const msg = ref('')
const today = new Date().toISOString().slice(0, 10)
const soon = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10)
const rows = computed(() => (stock.data.value || []).filter((r) =>
  !q.value || `${r.goods_code} ${r.goods_desc}`.toLowerCase().includes(q.value.toLowerCase())))

async function recheck() {
  const r = await post('/api/v1/inventory/material-requests', {})
  msg.value = r.released_orders.length ? t('stock.released', { list: r.released_orders.join(', ') }) : t('stock.stillShort')
  requests.reload(); stock.reload()
}
const exp = (d) => (!d ? null : d < today ? 'expired' : d <= soon ? 'soon' : null)
</script>

<template>
  <PageHead :title="t('stock.title')" :subtitle="t('stock.subtitle')" />

  <section v-if="requests.data.value?.length" class="card stack short">
    <div class="row">
      <h2 class="grow"><Icon name="alert" :size="20" /> {{ t('stock.requests') }}</h2>
      <button class="btn btn-primary" @click="recheck">{{ t('stock.recheck') }}</button>
    </div>
    <p v-if="msg" class="notice notice-ok" role="status">{{ msg }}</p>
    <div class="table-wrap"><table class="table">
      <thead><tr><th>{{ t('stock.code') }}</th><th>{{ t('stock.desc') }}</th><th>{{ t('stock.short') }}</th><th>WO</th><th>{{ t('wo.due') }}</th></tr></thead>
      <tbody><tr v-for="r in requests.data.value" :key="r.id"><td class="mono">{{ r.goods_code }}</td><td>{{ r.goods_desc }}</td>
        <td><strong>{{ r.qty_short.toLocaleString() }}</strong></td><td class="mono">{{ r.wo_id }}</td><td>{{ r.needed_by }}</td></tr></tbody>
    </table></div>
  </section>

  <div class="card">
    <label class="field search"><span>{{ t('common.search') }}</span><input v-model="q" :placeholder="t('stock.code')" /></label>
    <p v-if="stock.error.value" class="notice notice-error">{{ stock.error.value }}</p>
    <div class="table-wrap"><table class="table">
      <thead><tr><th></th><th>{{ t('stock.code') }}</th><th>{{ t('stock.desc') }}</th><th class="num">{{ t('stock.onhand') }}</th>
        <th class="num">{{ t('stock.reserved') }}</th><th class="num">{{ t('stock.available') }}</th></tr></thead>
      <tbody>
        <template v-for="r in rows" :key="r.goods_code">
          <tr>
            <td><button class="btn btn-quiet tiny" :aria-expanded="!!open[r.goods_code]" @click="open[r.goods_code] = !open[r.goods_code]"
                        :aria-label="`${r.goods_code} lots`">{{ open[r.goods_code] ? '−' : '+' }}</button></td>
            <td class="mono">{{ r.goods_code }}</td><td>{{ r.goods_desc }}</td><td class="num">{{ r.on_hand.toLocaleString() }}</td>
            <td class="num">{{ r.reserved.toLocaleString() }}</td>
            <td class="num"><strong>{{ r.available.toLocaleString() }}</strong></td>
          </tr>
          <tr v-if="open[r.goods_code]" class="lots"><td></td><td colspan="5">
            <table class="table inner"><thead><tr><th>Lot</th><th>{{ t('stock.bin') }}</th><th>Zone</th><th class="num">{{ t('common.qty') }}</th><th>{{ t('stock.expiry') }}</th></tr></thead>
              <tbody><tr v-for="l in r.lots" :key="l.lot_number + l.bin_name"><td class="mono">{{ l.lot_number || '–' }}</td><td class="mono">{{ l.bin_name }}</td>
                <td>{{ l.zone }}</td><td class="num">{{ l.qty.toLocaleString() }}</td>
                <td>{{ l.expiry_date || '–' }}
                  <span v-if="exp(l.expiry_date) === 'expired'" class="pill pill-alarm"><Icon name="x" :size="12" /> {{ t('stock.expired') }}</span>
                  <span v-else-if="exp(l.expiry_date) === 'soon'" class="pill pill-warn"><Icon name="alert" :size="12" /> {{ t('stock.soon') }}</span></td></tr></tbody></table>
          </td></tr>
        </template>
      </tbody>
    </table></div>
  </div>
</template>

<style scoped>
.short { margin-bottom: 20px; border-color: var(--warn); }
.short h2 { display: flex; gap: 8px; align-items: center; font-size: var(--text-lg); }
.grow { flex: 1; }
.search { max-width: 320px; margin-bottom: 12px; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.tiny { min-height: 32px; padding: 0 10px; }
.lots > td { background: var(--surface-2); }
.inner th, .inner td { padding: 6px 10px; }
</style>
