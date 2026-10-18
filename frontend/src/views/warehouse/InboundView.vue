<script setup>
// Receive goods into a bin. Waiting orders are re-checked straight after.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, post } from '../../api/client.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import GoodsPicker from '../../components/GoodsPicker.vue'

const { t } = useI18n()
const bins = usePolled(() => get('/api/v1/inventory/bins'), 0)
const recent = usePolled(() => get('/api/v1/inventory/movements'), 15000)
const blank = () => ({ goods_code: '', qty: '', bin_name: '', lot_number: '', expiry_date: '', ref: '' })
const form = ref(blank())
const msg = ref({ text: '', kind: 'ok' })
const busy = ref(false)

async function receive() {
  busy.value = true
  try {
    const r = await post('/api/v1/inventory/receive', form.value)
    msg.value = { kind: 'ok', text: t('inbound.done', { qty: form.value.qty, code: form.value.goods_code, bin: r.bin_name })
      + (r.released_orders.length ? ' ' + t('stock.released', { list: r.released_orders.join(', ') }) : '') }
    form.value = blank(); recent.reload()
  } catch (e) { msg.value = { kind: 'error', text: e.message } } finally { busy.value = false }
}
</script>

<template>
  <PageHead :title="t('nav.inbound')" :subtitle="t('inbound.subtitle')" />
  <form class="card form" @submit.prevent="receive">
    <GoodsPicker v-model="form.goods_code" :label="t('stock.code')" />
    <label class="field"><span>{{ t('common.qty') }}</span><input v-model.number="form.qty" type="number" min="1" required /></label>
    <label class="field"><span>{{ t('stock.bin') }}</span>
      <select v-model="form.bin_name" required><option value="" disabled>—</option>
        <option v-for="b in (bins.data.value?.bins || []).filter((b) => ['RAW', 'GENERAL', 'FG'].includes(b.zone))" :key="b.bin_name" :value="b.bin_name">{{ b.bin_name }} · {{ b.zone }}</option></select></label>
    <label class="field"><span>{{ t('inbound.lot') }}</span><input v-model="form.lot_number" /></label>
    <label class="field"><span>{{ t('stock.expiry') }}</span><input v-model="form.expiry_date" type="date" /></label>
    <label class="field"><span>{{ t('inbound.ref') }}</span><input v-model="form.ref" placeholder="PO / ASN" /></label>
    <div class="row full">
      <button class="btn btn-primary" :disabled="busy">{{ t('inbound.receive') }}</button>
      <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>
    </div>
  </form>
  <section class="card table-wrap block">
    <h2>{{ t('inbound.recent') }}</h2>
    <table class="table"><thead><tr><th>Time</th><th>Type</th><th>{{ t('stock.code') }}</th><th>Lot</th><th>{{ t('stock.bin') }}</th><th>{{ t('common.qty') }}</th><th>Ref</th><th>By</th></tr></thead>
      <tbody><tr v-for="m in (recent.data.value || []).slice(0, 40)" :key="m.id"><td>{{ $dt(m.ts) }}</td><td>{{ m.kind }}</td>
        <td class="mono">{{ m.goods_code }}</td><td class="mono">{{ m.lot_number }}</td><td class="mono">{{ m.bin_to || m.bin_from }}</td>
        <td>{{ m.qty }}</td><td class="mono">{{ m.ref }}</td><td>{{ m.actor }}</td></tr></tbody></table>
  </section>
</template>

<style scoped>
.form { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.full { grid-column: 1 / -1; }
.block { margin-top: 20px; }
.block h2 { margin-bottom: 12px; font-size: var(--text-lg); }
</style>
