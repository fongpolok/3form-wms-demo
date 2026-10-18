<script setup>
import { fmtDateTime } from '../../i18n/index.js'
// Trace-back for EM / PIC. Only the PIC may correct records, always with a reason.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, patch } from '../../api/client.js'
import { useSession } from '../../composables/session.js'
import PageHead from '../../components/PageHead.vue'

const { t } = useI18n()
const session = useSession()
const lookup = ref('')
const wips = ref([])
const events = ref([])
const error = ref('')
const notice = ref('')
const editing = ref(null)   // { kind: 'wip'|'event', id, field, value, reason }

async function find() {
  error.value = ''; notice.value = ''
  const id = lookup.value.trim()
  const key = id.startsWith('WO-') ? 'wo_id' : 'batch_id'
  try {
    ;[wips.value, events.value] = await Promise.all([
      get(`/api/v1/mes/wip?${key}=${encodeURIComponent(id)}`),
      get(`/api/v1/mes/events?${key}=${encodeURIComponent(id)}`),
    ])
  } catch (e) { error.value = e.message }
}

function edit(kind, id, field, value) { editing.value = { kind, id, field, value, reason: '' } }

async function saveEdit() {
  const e = editing.value
  const url = e.kind === 'wip' ? `/api/v1/mes/wip/${e.id}` : `/api/v1/mes/events/${e.id}`
  try {
    await patch(url, { changes: { [e.field]: Number(e.value) }, reason: e.reason })
    editing.value = null
    notice.value = t('scrap.saved')
    find()
  } catch (err) { error.value = err.message }
}
const fmt = (ts) => fmtDateTime(ts)
</script>

<template>
  <PageHead :title="t('scrap.title')" :subtitle="t('scrap.subtitle')" />
  <form class="row card" @submit.prevent="find">
    <label class="field grow"><span>{{ t('scrap.lookup') }}</span><input v-model="lookup" class="mono" placeholder="B-20261019-0001" /></label>
    <button class="btn btn-primary" :disabled="!lookup">{{ t('scrap.find') }}</button>
  </form>
  <p v-if="!session.can('PIC')" class="muted note">{{ t('scrap.pickOnly') }}</p>
  <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
  <p v-if="notice" class="notice notice-ok" role="status">{{ notice }}</p>

  <section v-if="editing" class="card stack edit" aria-labelledby="edit-title">
    <h2 id="edit-title">{{ editing.kind === 'wip' ? t('scrap.editWip') : t('scrap.editEvent') }} · <span class="mono">{{ editing.id }}</span></h2>
    <label class="field"><span>{{ editing.field }}</span><input v-model="editing.value" type="number" min="0" /></label>
    <label class="field"><span>{{ t('scrap.reasonRequired') }}</span><textarea v-model="editing.reason" required></textarea></label>
    <div class="row">
      <button class="btn btn-primary" :disabled="!editing.reason.trim()" @click="saveEdit">{{ t('common.save') }}</button>
      <button class="btn" @click="editing = null">{{ t('common.cancel') }}</button>
    </div>
  </section>

  <section v-if="wips.length" class="card table-wrap block">
    <h2>{{ t('scrap.wip') }}</h2>
    <table class="table">
      <thead><tr><th>WIP</th><th>Station</th><th>In</th><th>Good</th><th>Scrap</th><th>Downtime</th><th>Started</th><th></th></tr></thead>
      <tbody>
        <tr v-for="w in wips" :key="w.wip_id">
          <td class="mono">{{ w.wip_id }} <span v-if="w.edited_by_pic" class="pill pill-warn">PIC</span></td>
          <td>{{ w.workstation }}</td><td>{{ w.qty_in }}</td><td>{{ w.good_qty ?? '–' }}</td><td>{{ w.scrap_qty }}</td>
          <td>{{ Math.round((w.downtime_seconds || 0) / 60) }} min</td><td>{{ fmt(w.started_at) }} · #{{ w.started_by }}</td>
          <td><button v-if="session.can('PIC') && w.good_qty != null" class="btn" @click="edit('wip', w.wip_id, 'good_qty', w.good_qty)">{{ t('common.edit') }}</button></td>
        </tr>
      </tbody>
    </table>
  </section>

  <section v-if="events.length" class="card table-wrap block">
    <h2>{{ t('scrap.events') }}</h2>
    <table class="table">
      <thead><tr><th>Time</th><th>Type</th><th>Station</th><th>Qty / value</th><th>Reason</th><th>Staff</th><th></th></tr></thead>
      <tbody>
        <tr v-for="e in events" :key="e.event_id">
          <td>{{ fmt(e.ts) }}</td><td>{{ e.type }} <span v-if="e.edited_by_pic" class="pill pill-warn">PIC</span></td>
          <td>{{ e.workstation }}</td><td>{{ e.qty ?? e.value ?? '' }}</td><td>{{ e.reason_code || '' }} {{ e.note || '' }}</td>
          <td>#{{ e.staff_id }}</td>
          <td><button v-if="session.can('PIC') && e.type === 'scrap'" class="btn" @click="edit('event', e.event_id, 'qty', e.qty)">{{ t('common.edit') }}</button></td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.grow { flex: 1; }
.block, .edit { margin-top: 20px; }
.block h2 { margin-bottom: 12px; }
.note { margin-top: 12px; }
</style>
