<script setup>
// Plan page: the same open orders planned by Built-in and by NVIDIA cuOpt, side by side (nothing is saved).
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { post, SLOW_MS } from '../api/client.js'
import { fmtDateTime } from '../i18n/index.js'

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
      <h3>{{ t('compare.moved', { n: result.orders.length }) }}</h3>
      <p v-if="!result.orders.length" class="muted">{{ t('compare.same') }}</p>
      <div v-else class="table-wrap">
        <table class="table">
          <thead><tr><th>WO</th><th>{{ t('wo.productName') }}</th><th>{{ t('wo.due') }}</th><th>{{ t('optimiser.builtin') }}</th>
            <th>{{ t('optimiser.cuopt') }}</th><th>{{ t('compare.change') }}</th></tr></thead>
          <tbody>
            <tr v-for="o in result.orders" :key="o.wo_id">
              <td class="mono">{{ o.wo_id }} <span v-if="o.urgent" class="pill pill-alarm">{{ t('progress.urgent') }}</span></td>
              <td>{{ o.product_name }}</td><td>{{ o.due_date }}</td>
              <td>{{ fmtDateTime(o.builtin_finish) }} <span v-if="o.builtin_late" class="pill pill-alarm">{{ t('plan.lateRisk') }}</span></td>
              <td>{{ fmtDateTime(o.cuopt_finish) }} <span v-if="o.cuopt_late" class="pill pill-alarm">{{ t('plan.lateRisk') }}</span></td>
              <td><span :class="['pill', o.delta_hours < 0 ? 'pill-ok' : 'pill-warn']">{{ o.delta_hours < 0 ? t('compare.earlier') : t('compare.later') }} {{ hrs(o.delta_hours) }}</span></td>
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
</style>
