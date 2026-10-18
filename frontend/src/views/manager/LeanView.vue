<script setup>
// DMAIC "Measure" + "Control": OEE, yield, sigma level, scrap Pareto, SPC.
// One filter row (date range) above all charts; every chart has a table view.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { get } from '../../api/client.js'
import { pick } from '../../i18n/index.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'
import ChartFrame from '../../components/charts/ChartFrame.vue'
import HBarChart from '../../components/charts/HBarChart.vue'
import SpcChart from '../../components/charts/SpcChart.vue'

const { t } = useI18n()
const iso = (d) => d.toISOString().slice(0, 10)
const RANGES = [7, 30, 90]
const days = ref(30)
const to = ref(iso(new Date()))
const from = ref(iso(new Date(Date.now() - 30 * 864e5)))
const data = ref(null)
const spc = ref(null)
const error = ref('')
const loading = ref(false)

function setDays(n) {
  days.value = n
  to.value = iso(new Date())
  from.value = iso(new Date(Date.now() - n * 864e5))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    ;[data.value, spc.value] = await Promise.all([
      get(`/api/v1/lean/summary?from=${from.value}&to=${to.value}`),
      get('/api/v1/lean/spc'),
    ])
  } catch (e) { error.value = e.message } finally { loading.value = false }
}
watch([from, to], load, { immediate: true })

const avg = (xs) => { const v = xs.filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null }
const oeeAvg = computed(() => avg((data.value?.oee || []).map((r) => r.oee)))
const oeeItems = computed(() => (data.value?.oee || []).map((r) => ({
  key: r.workstation, label: `${r.workstation} ${pick(r.step_name)}`, value: r.oee, valueLabel: r.oee == null ? '–' : `${r.oee}%`,
  tip: r.oee == null ? ['No finished batches'] : [`Availability ${r.availability}%`, `Performance ${r.performance}%`,
    `Quality ${r.quality}%`, `${r.batches} batches · ${r.downtime_min} min stopped`],
})))
const pareto = computed(() => {
  let crossed = false
  return (data.value?.pareto || []).map((p) => {
    const vital = !crossed
    if (p.cum_pct >= 80) crossed = true
    return { key: p.reason_code, label: pick(p.label), value: p.qty, emphasis: vital,
             valueLabel: `${p.qty} · ${p.cum_pct}%`, tip: [`${p.qty} pieces in ${p.events} records`, `Cumulative ${p.cum_pct}%`] }
  })
})
const vitalFew = computed(() => pareto.value.filter((p) => p.emphasis).map((p) => p.label))
const fpyItems = computed(() => (data.value?.yields.steps || []).map((s) => ({
  key: s.step_code, label: pick(s.step_name), value: s.fpy, valueLabel: s.fpy == null ? '–' : `${s.fpy}%`,
  tip: [`${s.good} good of ${s.qty_in} received`],
})))
const cpkState = computed(() => {
  const c = spc.value?.cpk
  if (c == null) return null
  return c >= 1.33 ? { cls: 'pill-ok', icon: 'check', text: 'Capable (≥ 1.33)' }
    : c >= 1 ? { cls: 'pill-warn', icon: 'alert', text: 'Marginal (1.00–1.33)' }
      : { cls: 'pill-alarm', icon: 'alert', text: 'Not capable (< 1.00)' }
})
</script>

<template>
  <PageHead :title="t('nav.lean')" :subtitle="t('lean.subtitle')" />

  <form class="card filters" @submit.prevent role="search">
    <div class="seg" role="radiogroup" :aria-label="t('lean.range')">
      <button v-for="n in RANGES" :key="n" type="button" role="radio" :aria-checked="days === n"
              :class="{ on: days === n }" @click="setDays(n)">{{ t('lean.lastDays', { n }) }}</button>
    </div>
    <label class="field"><span>{{ t('common.from') }}</span><input type="date" v-model="from" @change="days = 0" /></label>
    <label class="field"><span>{{ t('common.to') }}</span><input type="date" v-model="to" @change="days = 0" /></label>
    <span v-if="loading" class="muted">{{ t('common.loading') }}</span>
  </form>
  <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>

  <template v-if="data">
    <div class="tiles">
      <div class="tile"><span class="label">{{ t('lean.oee') }}</span><span class="value">{{ oeeAvg == null ? '–' : oeeAvg.toFixed(1) + '%' }}</span><span class="muted note">{{ t('lean.oeeNote') }}</span></div>
      <div class="tile"><span class="label">{{ t('lean.rty') }}</span><span class="value">{{ data.yields.rty ?? '–' }}%</span><span class="muted note">{{ t('lean.rtyNote') }}</span></div>
      <div class="tile"><span class="label">DPMO</span><span class="value">{{ data.yields.dpmo?.toLocaleString() ?? '–' }}</span><span class="muted note">{{ data.yields.defects.toLocaleString() }} / {{ data.yields.units.toLocaleString() }} {{ t('lean.pieces') }}</span></div>
      <div class="tile"><span class="label">{{ t('lean.sigma') }}</span><span class="value">{{ data.yields.sigma ?? '–' }}σ</span><span class="muted note">{{ t('lean.sigmaNote') }}</span></div>
      <div class="tile" v-if="spc"><span class="label">Cpk · {{ spc.measure }}</span><span class="value">{{ spc.cpk ?? '–' }}</span>
        <span v-if="cpkState" :class="['pill', cpkState.cls]"><Icon :name="cpkState.icon" :size="14" /> {{ cpkState.text }}</span></div>
    </div>

    <div class="grid2">
      <ChartFrame :title="t('lean.oeeByStation')" :subtitle="t('lean.oeeSub')">
        <HBarChart :items="oeeItems" :max="100" :label-width="150" />
        <template #table>
          <table class="table"><thead><tr><th>{{ t('nav.workstations') }}</th><th>OEE</th><th>A</th><th>P</th><th>Q</th><th>{{ t('progress.batches') }}</th></tr></thead>
            <tbody><tr v-for="r in data.oee" :key="r.workstation"><td>{{ r.workstation }} {{ pick(r.step_name) }}</td><td>{{ r.oee ?? '–' }}</td><td>{{ r.availability ?? '–' }}</td><td>{{ r.performance ?? '–' }}</td><td>{{ r.quality ?? '–' }}</td><td>{{ r.batches }}</td></tr></tbody></table>
        </template>
      </ChartFrame>

      <ChartFrame :title="t('lean.pareto')" :subtitle="vitalFew.length ? t('lean.paretoSub', { list: vitalFew.join(', ') }) : t('common.none')">
        <HBarChart :items="pareto" :label-width="150" />
        <template #table>
          <table class="table"><thead><tr><th>{{ t('common.reason') }}</th><th>{{ t('common.qty') }}</th><th>{{ t('lean.cum') }}</th></tr></thead>
            <tbody><tr v-for="p in data.pareto" :key="p.reason_code"><td>{{ pick(p.label) }}</td><td>{{ p.qty }}</td><td>{{ p.cum_pct }}%</td></tr></tbody></table>
        </template>
      </ChartFrame>
    </div>

    <ChartFrame v-if="spc && spc.points.length" :title="t('lean.spcTitle', { m: spc.measure, step: pick(spc.step_name) })"
                :subtitle="spc.ucl ? t('lean.spcSub', { n: spc.n, breaks: spc.violations.length }) : spc.note" class="block">
      <SpcChart :data="spc" />
      <template #table>
        <table class="table"><thead><tr><th>#</th><th>Time</th><th>{{ t('worker.value') }}</th><th>Batch</th><th></th></tr></thead>
          <tbody><tr v-for="(p, i) in spc.points" :key="i"><td>{{ i + 1 }}</td><td>{{ $dt(p.ts) }}</td><td>{{ p.value }}</td><td class="mono">{{ p.batch_id }}</td>
            <td><span v-if="spc.violations.some((v) => v.index === i)" class="pill pill-alarm">!</span></td></tr></tbody></table>
      </template>
    </ChartFrame>

    <ChartFrame :title="t('lean.fpy')" :subtitle="t('lean.fpySub')" class="block">
      <HBarChart :items="fpyItems" :max="100" :label-width="150" />
      <template #table>
        <table class="table"><thead><tr><th>{{ t('worker.step') }}</th><th>FPY</th><th>In</th><th>Good</th></tr></thead>
          <tbody><tr v-for="s in data.yields.steps" :key="s.step_code"><td>{{ pick(s.step_name) }}</td><td>{{ s.fpy ?? '–' }}</td><td>{{ s.qty_in }}</td><td>{{ s.good }}</td></tr></tbody></table>
      </template>
    </ChartFrame>
  </template>
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end; margin-bottom: 20px; }
.filters .field { width: 170px; }
.seg { display: inline-flex; border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 2px; align-self: flex-end; }
.seg button { min-height: 40px; padding: 0 14px; border: 0; border-radius: 8px; background: transparent; color: var(--ink-2); font: 600 var(--text-sm)/1 var(--font-body); cursor: pointer; }
.seg button.on { background: var(--surface-2); color: var(--ink); box-shadow: 0 0 0 1px var(--line-strong); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }
.tile { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-lg); padding: 16px 18px; display: grid; gap: 4px; align-content: start; }
.tile .label { font-size: var(--text-sm); color: var(--ink-2); font-weight: 600; }
.tile .value { font-size: 2rem; font-weight: 700; font-variant-numeric: proportional-nums; line-height: 1.1; }
.tile .note { font-size: 0.8125rem; }
.tile .pill { justify-self: start; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }
.block { margin-top: 16px; }
@media (max-width: 520px) { .grid2 { grid-template-columns: 1fr; } }
</style>
