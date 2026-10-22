<script setup>
// Ship to a client from stock. Shows which lots will be picked (FEFO / FIFO) first, and the walking order.
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, post, SLOW_MS } from '../../api/client.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import GoodsPicker from '../../components/GoodsPicker.vue'
import PickRoute from '../../components/PickRoute.vue'

const { t } = useI18n()
const shipments = usePolled(() => get('/api/v1/inventory/shipments'), 20000)
const client = ref('')
const line = ref({ goods_code: '', qty: '' })
const preview = ref(null)
const route = ref(null)
const msg = ref({ text: '', kind: 'ok' })

watch(() => [line.value.goods_code, line.value.qty], () => { route.value = null })
async function planRoute() {
  try { route.value = await post('/api/v1/inventory/pick-route', { lines: [line.value] }, { timeoutMs: SLOW_MS }); msg.value = { text: '', kind: 'ok' } }
  catch (e) { route.value = null; msg.value = { kind: 'error', text: e.message } }
}
watch(() => line.value.goods_code, async (code) => {
  preview.value = code ? await get(`/api/v1/inventory/pick-preview/${encodeURIComponent(code)}`).catch(() => null) : null
})
async function ship() {
  try {
    const r = await post('/api/v1/inventory/shipments', { client: client.value, lines: [line.value] })
    msg.value = { kind: 'ok', text: t('outbound.done', { id: r.shipment_id }) }
    line.value = { goods_code: '', qty: '' }; shipments.reload()
  } catch (e) { msg.value = { kind: 'error', text: e.message } }
}
</script>

<template>
  <PageHead :title="t('nav.outbound')" :subtitle="t('outbound.subtitle')" />
  <form class="card form" @submit.prevent="ship">
    <label class="field"><span>{{ t('wo.client') }}</span><input v-model="client" required /></label>
    <GoodsPicker v-model="line.goods_code" :label="t('stock.code')" />
    <label class="field"><span>{{ t('common.qty') }}</span><input v-model.number="line.qty" type="number" min="1" required /></label>
    <div v-if="preview" class="full preview">
      <p><strong>{{ t('stock.available') }}: {{ preview.available }}</strong> · {{ t('outbound.rule') }}: {{ preview.rule.toUpperCase() }}</p>
      <ol><li v-for="l in preview.lots.slice(0, 5)" :key="l.lot_number + l.bin_name" class="mono">{{ l.lot_number || '–' }} · {{ l.bin_name }} · {{ l.qty }} · {{ l.expiry_date || '—' }}</li></ol>
    </div>
    <PickRoute v-if="route" :route="route" class="full" />
    <div class="row full">
      <button type="button" class="btn" :disabled="!line.goods_code || !line.qty" @click="planRoute">{{ t('pick.route') }}</button>
      <button class="btn btn-primary">{{ t('outbound.ship') }}</button>
      <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>
    </div>
  </form>
  <section class="card table-wrap block">
    <h2>{{ t('outbound.recent') }}</h2>
    <table class="table"><thead><tr><th>ID</th><th>Time</th><th>{{ t('wo.client') }}</th><th>{{ t('outbound.from') }}</th><th>{{ t('outbound.lines') }}</th></tr></thead>
      <tbody><tr v-for="s in (shipments.data.value || []).slice(0, 40)" :key="s.shipment_id"><td class="mono">{{ s.shipment_id }}</td>
        <td>{{ $dt(s.shipped_at) }}</td><td>{{ s.client }}</td><td>{{ s.source === 'direct' ? t('wo.direct') : t('wo.stock') }}</td>
        <td class="mono">{{ s.lines.map((l) => `${l.goods_code} ${l.lot_number} ×${l.qty}`).join('; ') }}</td></tr></tbody></table>
  </section>
</template>

<style scoped>
.form { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.full { grid-column: 1 / -1; }
.preview { background: var(--surface-2); border-radius: var(--radius); padding: 12px 16px; }
.preview ol { margin: 6px 0 0; padding-left: 1.4em; font-size: var(--text-sm); }
.block { margin-top: 20px; }
.block h2 { margin-bottom: 12px; font-size: var(--text-lg); }
</style>
