<script setup>
// ERP inbox: orders from SAP / Oracle that did not fit (unknown product, bad qty / date).
// The PIC fixes and approves, or rejects. Below: results waiting to go back to the ERP.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, post } from '../../api/client.js'
import { fmtDateTime } from '../../i18n/index.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import GoodsPicker from '../../components/GoodsPicker.vue'

const { t } = useI18n()
const data = usePolled(() => get('/api/v1/integrations/erp-inbox'), 30000)
const edits = ref({})
const msg = ref({ text: '', kind: 'ok' })
const busy = ref(false)

function editOf(i) {
  const k = `${i.conn_id}:${i.erp_ref}`
  edits.value[k] ||= { product_code: i.order.product_code, qty: i.order.qty, due_date: String(i.order.due_date).slice(0, 10) }
  return edits.value[k]
}
async function decide(i, approve) {
  try {
    const r = await post('/api/v1/integrations/erp-inbox', { erp_ref: i.erp_ref, conn_id: i.conn_id, approve, edits: approve ? editOf(i) : undefined })
    msg.value = { kind: 'ok', text: approve ? t('erp.imported', { wo: r.wo_id }) : t('erp.rejectedMsg') }
    data.reload()
  } catch (e) { msg.value = { kind: 'error', text: e.message } }
}
async function syncNow() {
  busy.value = true
  try { const r = await post('/api/v1/integrations/erp-sync', {}); msg.value = { kind: 'ok', text: t('erp.synced', { n: r.results.length }) }; data.reload() }
  catch (e) { msg.value = { kind: 'error', text: e.message } } finally { busy.value = false }
}
</script>

<template>
  <PageHead :title="t('nav.erpInbox')" :subtitle="t('erp.subtitle')">
    <button class="btn btn-primary" :disabled="busy" @click="syncNow">{{ busy ? t('common.loading') : t('erp.syncNow') }}</button>
  </PageHead>
  <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>
  <p v-if="data.data.value && !data.data.value.inbox.length" class="muted">{{ t('erp.empty') }}</p>
  <div class="stack">
    <article v-for="i in data.data.value?.inbox || []" :key="i.conn_id + i.erp_ref" class="card item">
      <div class="row"><span class="pill pill-info">{{ i.system }}</span><strong class="mono">{{ i.erp_ref }}</strong>
        <span class="muted small">{{ fmtDateTime(i.received_at) }} · {{ i.order.client }}</span></div>
      <ul class="problems"><li v-for="p in i.problems" :key="p">{{ p }}</li></ul>
      <div class="form">
        <GoodsPicker v-model="editOf(i).product_code" :label="t('wo.product')" />
        <label class="field"><span>{{ t('wo.qty') }}</span><input v-model="editOf(i).qty" type="number" min="1" /></label>
        <label class="field"><span>{{ t('wo.due') }}</span><input v-model="editOf(i).due_date" type="date" /></label>
      </div>
      <div class="row"><button class="btn btn-primary" @click="decide(i, true)">{{ t('erp.approve') }}</button>
        <button class="btn" @click="decide(i, false)">{{ t('erp.reject') }}</button></div>
    </article>
  </div>
  <section class="card table-wrap block">
    <h2>{{ t('erp.outbox') }}</h2>
    <p v-if="!(data.data.value?.outbox || []).length" class="muted">{{ t('common.none') }}</p>
    <table v-else class="table"><thead><tr><th>WO</th><th>ERP</th><th>{{ t('erp.good') }}</th><th>{{ t('erp.scrap') }}</th><th>{{ t('common.status') }}</th><th>{{ t('erp.detail') }}</th></tr></thead>
      <tbody><tr v-for="o in data.data.value.outbox" :key="o.wo_id"><td class="mono">{{ o.wo_id }}</td><td class="mono">{{ o.result.erp_ref }}</td>
        <td>{{ o.result.good_qty }}</td><td>{{ o.result.scrap_qty }}</td>
        <td><span :class="['pill', o.status === 'sent' ? 'pill-ok' : o.attempts ? 'pill-alarm' : 'pill-warn']">{{ t(`erp.status.${o.status}`) }}</span></td>
        <td class="small">{{ o.status === 'sent' ? `${o.erp_confirmation} · ${fmtDateTime(o.sent_at)}` : (o.last_error || '–') }}<template v-if="o.attempts"> · {{ o.attempts }}×</template></td></tr></tbody></table>
  </section>
</template>

<style scoped>
.item { display: grid; gap: 10px; }
.problems { margin: 0; padding-left: 1.2em; color: var(--warn); }
.form { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.small { font-size: 0.8125rem; }
.block { margin-top: 16px; }
.block h2 { font-size: var(--text-lg); margin-bottom: 10px; }
</style>
