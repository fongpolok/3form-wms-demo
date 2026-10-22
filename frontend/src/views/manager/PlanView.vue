<script setup>
// APS plan: published plan (or the waiting draft) as a Gantt chart, the order list
// with LATE RISK, orders blocked by material, and Accept / Reject for a draft.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, post, SLOW_MS } from '../../api/client.js'
import { fmtDateTime } from '../../i18n/index.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'
import GanttChart from '../../components/charts/GanttChart.vue'
import CompareEngines from '../../components/CompareEngines.vue'

const { t } = useI18n()
const published = usePolled(() => get('/api/v1/aps/plan?status=published'), 30000)
const draft = usePolled(() => get('/api/v1/aps/plan?status=draft'), 30000)
const stations = usePolled(() => get('/api/v1/mes/workstations'), 0)
const show = ref('published')
const hours = ref(48)
const selected = ref(null)
const busy = ref(false)
const msg = ref({ text: '', kind: 'ok' })

const plan = computed(() => (show.value === 'draft' && draft.data.value) || published.data.value)
const lateIds = computed(() => (plan.value?.orders || []).filter((o) => o.late_risk).map((o) => o.wo_id))
const stationNames = computed(() => Object.fromEntries((stations.data.value || []).map((s) => [s.code, s.step_name])))

async function replan() {
  busy.value = true
  try { await post('/api/v1/aps/replan', {}, { timeoutMs: SLOW_MS }); await draft.reload(); show.value = 'draft'; msg.value = { kind: 'ok', text: t('plan.draftReady') } }
  catch (e) { msg.value = { kind: 'error', text: e.message } } finally { busy.value = false }
}
async function decide(accept) {
  busy.value = true
  try {
    await post(`/api/v1/aps/plans/${draft.data.value.plan_id}/decision`, { accept })
    msg.value = { kind: 'ok', text: accept ? t('plan.accepted') : t('plan.rejected') }
    show.value = 'published'; await Promise.all([published.reload(), draft.reload()])
  } catch (e) { msg.value = { kind: 'error', text: e.message } } finally { busy.value = false }
}
const cal = usePolled(() => get('/api/v1/aps/calendar'), 0)
const todayHoliday = computed(() => {
  const today = new Date().toLocaleDateString('en-CA')
  return (cal.data.value?.holidays || []).find((h) => h.date === today)?.name
})
const hrs = (h) => (h == null ? '–' : `${h > 0 ? '+' : ''}${h} h`)
</script>

<template>
  <PageHead :title="t('nav.plan')" :subtitle="t('plan.subtitle')">
    <button class="btn btn-primary" :disabled="busy" @click="replan">{{ t('plan.replan') }}</button>
  </PageHead>
  <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>

  <CompareEngines />

  <!-- Draft waiting for approval -->
  <section v-if="draft.data.value" class="card stack draft">
    <div class="row">
      <div class="grow">
        <h2><Icon name="alert" :size="20" /> {{ t('plan.draftTitle') }}</h2>
        <p class="muted">{{ draft.data.value.reason }} · {{ fmtDateTime(draft.data.value.created_at) }} · {{ t('plan.moved', { n: draft.data.value.diff.moved_ops }) }}</p>
      </div>
      <div class="seg" role="radiogroup" :aria-label="t('plan.view')">
        <button type="button" role="radio" :aria-checked="show === 'published'" :class="{ on: show === 'published' }" @click="show = 'published'">{{ t('plan.current') }}</button>
        <button type="button" role="radio" :aria-checked="show === 'draft'" :class="{ on: show === 'draft' }" @click="show = 'draft'">{{ t('plan.draft') }}</button>
      </div>
      <button class="btn btn-primary" :disabled="busy" @click="decide(true)">{{ t('plan.accept') }}</button>
      <button class="btn" :disabled="busy" @click="decide(false)">{{ t('plan.reject') }}</button>
    </div>
    <ul v-if="draft.data.value.diff.orders.length" class="changes">
      <li v-for="d in draft.data.value.diff.orders" :key="d.wo_id">
        <span class="mono">{{ d.wo_id }}</span>
        <span :class="['pill', d.change === 'later' ? 'pill-warn' : d.change === 'earlier' ? 'pill-ok' : 'pill-info']">{{ t(`plan.change.${d.change}`) }}</span>
        <span v-if="d.delta_hours != null">{{ hrs(d.delta_hours) }}</span>
        <span class="muted">→ {{ fmtDateTime(d.after) }}</span>
      </li>
    </ul>
    <p v-else class="muted">{{ t('plan.noChange') }}</p>
  </section>

  <section v-if="plan" class="card stack">
    <div class="row">
      <div class="grow">
        <h2>{{ show === 'draft' && draft.data.value ? t('plan.draft') : t('plan.current') }} · <span class="mono">{{ plan.plan_id }}</span></h2>
        <p class="muted">{{ plan.published_by ? t('plan.publishedBy', { who: plan.published_by, when: fmtDateTime(plan.published_at) }) : fmtDateTime(plan.created_at) }}
          · {{ t('plan.engine') }}: {{ plan.engine === 'cuopt' ? t('plan.engineCuopt') : t('plan.engineBuiltin') }}</p>
        <p v-if="todayHoliday" class="pill pill-info holiday">{{ t('plan.holidayToday', { name: todayHoliday }) }}</p>
      </div>
      <div class="seg" role="radiogroup" :aria-label="t('plan.window')">
        <button v-for="h in [24, 48, 72, 168, 336]" :key="h" type="button" role="radio" :aria-checked="hours === h" :class="{ on: hours === h }" @click="hours = h">
          {{ h < 168 ? t('plan.nDays', h / 24) : t('plan.nWeeks', h / 168) }}</button>
      </div>
    </div>
    <GanttChart :plan="plan" :hours="hours" :selected="selected" :late-ids="lateIds" :station-names="stationNames" @select="selected = $event" />
  </section>
  <p v-else-if="!published.loading.value" class="muted">{{ t('plan.none') }}</p>

  <div v-if="plan" class="grid2">
    <section class="card table-wrap">
      <h2>{{ t('plan.orders') }}</h2>
      <table class="table">
        <thead><tr><th>WO</th><th>{{ t('wo.productName') }}</th><th>{{ t('wo.due') }}</th><th>{{ t('plan.finish') }}</th><th>{{ t('plan.slack') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-for="o in plan.orders" :key="o.wo_id" :class="{ selrow: selected === o.wo_id }" @click="selected = selected === o.wo_id ? null : o.wo_id">
            <td class="mono">{{ o.wo_id }} <span v-if="o.urgent" class="pill pill-alarm">{{ t('progress.urgent') }}</span></td>
            <td>{{ o.product_name || o.product_code }}</td><td>{{ o.due_date }}</td><td>{{ fmtDateTime(o.planned_finish) }}</td>
            <td>{{ o.slack_hours == null ? '–' : `${o.slack_hours} h` }}</td>
            <td><span v-if="o.late_risk" class="pill pill-alarm"><Icon name="alert" :size="12" /> {{ o.beyond_horizon ? t('plan.beyond') : t('plan.lateRisk') }}</span>
              <span v-else class="pill pill-ok"><Icon name="check" :size="12" /> {{ t('plan.onTime') }}</span></td>
          </tr>
        </tbody>
      </table>
    </section>
    <section class="card table-wrap">
      <h2>{{ t('plan.blocked') }}</h2>
      <p v-if="!plan.blocked.length" class="muted">{{ t('common.none') }}</p>
      <table v-else class="table">
        <thead><tr><th>WO</th><th>{{ t('wo.product') }}</th><th>{{ t('wo.due') }}</th><th>{{ t('stock.short') }}</th></tr></thead>
        <tbody><tr v-for="b in plan.blocked" :key="b.wo_id"><td class="mono">{{ b.wo_id }}</td><td>{{ b.product_code }}</td><td>{{ b.due_date }}</td>
          <td class="mono">{{ b.shortages.map((s) => `${s.goods_code} −${s.short}`).join(', ') }}</td></tr></tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.grow { flex: 1; min-width: 0; }
.holiday { margin-top: 6px; display: inline-flex; }
.draft { border-color: var(--accent); border-width: 2px; margin-bottom: 16px; }
.draft h2, .stack h2 { font-size: var(--text-lg); display: flex; gap: 8px; align-items: center; }
.changes { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.changes li { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.seg { display: inline-flex; border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 2px; }
.seg button { min-height: 36px; padding: 0 12px; border: 0; border-radius: 8px; background: transparent; color: var(--ink-2); font: 600 var(--text-sm)/1 var(--font-body); cursor: pointer; }
.seg button.on { background: var(--surface-2); color: var(--ink); box-shadow: 0 0 0 1px var(--line-strong); }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; margin-top: 16px; }
.grid2 h2 { font-size: var(--text-lg); margin-bottom: 12px; }
tbody tr { cursor: pointer; }
.selrow td { background: var(--accent-soft); }
.grid2 td.mono { white-space: nowrap; }
.grid2 .table { min-width: 620px; }
@media (max-width: 520px) { .grid2 { grid-template-columns: 1fr; } }
</style>
