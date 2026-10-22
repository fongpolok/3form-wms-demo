<script setup>
// Plan page: the same open orders planned by Built-in and by NVIDIA cuOpt, side by side (nothing is saved).
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { post, SLOW_MS } from '../api/client.js'
import { fmtDateTime } from '../i18n/index.js'
import ChartFrame from './charts/ChartFrame.vue'
import DumbbellChart from './charts/DumbbellChart.vue'

const { t } = useI18n()
const result = ref(null)
const error = ref('')
const busy = ref(false)
const ROWS = [
  { key: 'late_orders', better: 'lower' }, { key: 'hours_late', better: 'lower', unit: ' h' },
  { key: 'changeovers', better: 'lower' }, { key: 'changeover_minutes', better: 'lower', unit: ' min' },
  { key: 'all_done_by', better: 'earlier' },
]

async function run() {
  busy.value = true; error.value = ''; result.value = null
  try { result.value = await post('/api/v1/aps/compare', {}, { timeoutMs: SLOW_MS }) } catch (e) { error.value = e.message } finally { busy.value = false }
}
const show = (row, v) => (row.key === 'all_done_by' ? fmtDateTime(v) : `${v}${row.unit || ''}`)
function winner(row) {
  const a = result.value.builtin[row.key], b = result.value.cuopt[row.key]
  if (a === b) return ''
  return (row.better === 'earlier' ? new Date(b) < new Date(a) : b < a) ? 'cuopt' : 'builtin'
}
const secs = (v) => (v == null ? '–' : v < 0.1 ? '< 0.1 s' : `${v.toFixed(1)} s`)
const headline = computed(() => {
  const r = result.value
  if (!r) return ''
  const earlier = r.chart.filter((o) => new Date(o.cuopt_finish) < new Date(o.builtin_finish)).length
  const later = r.chart.filter((o) => new Date(o.cuopt_finish) > new Date(o.builtin_finish)).length
  return t('chart.headline', { earlier, later, n: r.chart.length, b: fmtDateTime(r.builtin.all_done_by), c: fmtDateTime(r.cuopt.all_done_by) })
})
const hoursApart = (o) => Math.round((new Date(o.cuopt_finish) - new Date(o.builtin_finish)) / 360000) / 10
const hrs = (h) => `${h > 0 ? '+' : ''}${h} h`
</script>

<template>
  <section class="card stack compare" aria-labelledby="cmp-title">
    <div class="row">
      <div class="grow">
        <h2 id="cmp-title">{{ t('compare.title') }}</h2>
        <p class="muted">{{ t('compare.help') }}</p>
      </div>
      <button class="btn" :disabled="busy" @click="run">{{ busy ? t('compare.running') : t('compare.run') }}</button>
    </div>
    <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
    <template v-if="result">
      <p class="headline">{{ headline }}</p>
      <dl class="size" :aria-label="t('chart.sizeTitle')">
        <div><dt>{{ t('chart.orders') }}</dt><dd>{{ result.cuopt.size.orders }}</dd></div>
        <div><dt>{{ t('chart.batches') }}</dt><dd>{{ result.cuopt.size.batches }}</dd></div>
        <div><dt>{{ t('chart.steps') }}</dt><dd>{{ result.cuopt.size.steps }}</dd></div>
        <div><dt>{{ t('chart.decisions') }}</dt><dd>{{ (result.cuopt.size.decisions ?? 0).toLocaleString() }}</dd></div>
        <div><dt><span class="mk-dot builtin"></span>{{ t('chart.planTime', { engine: t('optimiser.builtin') }) }}</dt><dd>{{ secs(result.builtin.size.seconds) }}</dd></div>
        <div><dt><span class="mk-dot cuopt"></span>{{ t('chart.planTime', { engine: t('optimiser.cuopt') }) }}</dt><dd>{{ secs(result.cuopt.size.seconds) }}</dd></div>
      </dl>
      <ChartFrame :title="t('chart.title')" :subtitle="t('chart.subtitle')">
        <DumbbellChart :rows="result.chart" />
        <template #table>
          <table class="table">
            <thead><tr><th>WO</th><th>{{ t('wo.productName') }}</th><th>{{ t('chart.target') }}</th><th>{{ t('optimiser.builtin') }}</th>
              <th>{{ t('optimiser.cuopt') }}</th><th>{{ t('compare.change') }}</th></tr></thead>
            <tbody><tr v-for="o in result.chart" :key="o.wo_id"><td class="mono">{{ o.wo_id }}</td><td>{{ o.product_name }}</td>
              <td>{{ fmtDateTime(o.target) }}</td>
              <td>{{ fmtDateTime(o.builtin_finish) }} <span v-if="o.builtin_late" class="pill pill-alarm">{{ t('plan.lateRisk') }}</span></td>
              <td>{{ fmtDateTime(o.cuopt_finish) }} <span v-if="o.cuopt_late" class="pill pill-alarm">{{ t('plan.lateRisk') }}</span></td>
              <td><span v-if="hoursApart(o)" :class="['pill', hoursApart(o) < 0 ? 'pill-ok' : 'pill-warn']">
                {{ hoursApart(o) < 0 ? t('compare.earlier') : t('compare.later') }} {{ hrs(hoursApart(o)) }}</span><span v-else>–</span></td></tr></tbody>
          </table>
        </template>
      </ChartFrame>
      <div class="table-wrap">
        <table class="table kpis">
          <thead><tr><th></th><th>{{ t('optimiser.builtin') }}</th><th>{{ t('optimiser.cuopt') }}</th></tr></thead>
          <tbody>
            <tr v-for="r in ROWS" :key="r.key">
              <th scope="row">{{ t(`compare.${r.key}`) }}</th>
              <td :class="{ win: winner(r) === 'builtin' }">{{ show(r, result.builtin[r.key]) }}</td>
              <td :class="{ win: winner(r) === 'cuopt' }">{{ show(r, result.cuopt[r.key]) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="muted small">{{ t('compare.howToUse') }}</p>
    </template>
  </section>
</template>

<style scoped>
.compare { margin-bottom: 16px; }
.compare h2 { font-size: var(--text-lg); }
.compare h3 { font-size: 1rem; margin: 8px 0 0; }
.grow { flex: 1; min-width: 0; }
.kpis { max-width: 640px; }
.kpis th[scope=row] { font-weight: 600; color: var(--ink); }
.win { font-weight: 700; color: var(--ok); }
.win::after { content: ' ✓'; }
.small { font-size: var(--text-sm); }
td.mono, td .pill { white-space: nowrap; }
.headline { font-size: 1.0625rem; font-weight: 600; color: var(--ink); margin: 0; }
.size { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; margin: 0; }
.size div { background: var(--surface-2); border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 12px; }
.size dt { font-size: 0.8125rem; color: var(--ink-2); display: flex; align-items: center; gap: 6px; }
.size dd { margin: 2px 0 0; font-size: 1.25rem; font-weight: 650; color: var(--ink); font-variant-numeric: tabular-nums; }
.mk-dot { width: 10px; height: 10px; flex: none; }
.mk-dot.builtin { background: var(--chart-builtin); border-radius: 50%; }
.mk-dot.cuopt { background: var(--chart-1); transform: rotate(45deg); border-radius: 2px; width: 9px; height: 9px; }
</style>
