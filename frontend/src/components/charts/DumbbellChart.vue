<script setup>
// When each order finishes: Built-in (orange circle) vs cuOpt (blue diamond), joined by a line, with the
// order's target finish as a thin tick. One row per order, HTML so text stays at real size.
// Shape + legend + tooltip carry identity, never colour alone (Apple HIG Charts; dataviz checks).
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { appLocale, fmtDateTime } from '../../i18n/index.js'

const props = defineProps({
  rows: { type: Array, required: true },   // [{ wo_id, product_name, target, builtin_finish, cuopt_finish, builtin_late, cuopt_late }]
  labelWidth: { type: Number, default: 170 },
})
const { t } = useI18n()
const hover = ref(null)
const ms = (v) => (v ? new Date(v).getTime() : null)

const range = computed(() => {
  const all = props.rows.flatMap((r) => [ms(r.target), ms(r.builtin_finish), ms(r.cuopt_finish)]).filter(Boolean)
  const lo = Math.min(...all), hi = Math.max(...all)
  const DAY = 86400000
  return { lo: Math.floor(lo / DAY) * DAY - 8 * 3600000, hi: Math.ceil(hi / DAY) * DAY - 8 * 3600000 + DAY }   // whole HK days
})
const pos = (v) => (v == null ? null : ((ms(v) - range.value.lo) / (range.value.hi - range.value.lo)) * 100)
const ticks = computed(() => {
  const out = []
  const days = (range.value.hi - range.value.lo) / 86400000
  const step = days > 14 ? 7 : days > 7 ? 2 : 1
  for (let d = 0; d <= days; d += step) {
    const at = range.value.lo + d * 86400000
    out.push({ at: (d / days) * 100, label: new Date(at).toLocaleDateString(appLocale(), { weekday: 'short', day: 'numeric' }) })
  }
  return out
})
const delta = (r) => {
  if (!r.builtin_finish || !r.cuopt_finish) return null
  return Math.round((ms(r.cuopt_finish) - ms(r.builtin_finish)) / 360000) / 10
}
const span = (r) => {
  const a = pos(r.builtin_finish), b = pos(r.cuopt_finish)
  return a == null || b == null ? null : { left: Math.min(a, b), width: Math.abs(a - b) }
}
const describe = (r) => {
  const d = delta(r)
  return `${r.wo_id}, ${r.product_name}. ${t('optimiser.builtin')} ${fmtDateTime(r.builtin_finish)}, ` +
    `${t('optimiser.cuopt')} ${fmtDateTime(r.cuopt_finish)}` + (d ? `, ${d < 0 ? t('compare.earlier') : t('compare.later')} ${Math.abs(d)} h` : '') +
    `. ${t('chart.target')} ${fmtDateTime(r.target)}.`
}
</script>

<template>
  <div class="dumbbell" :style="{ '--label-w': labelWidth + 'px' }">
    <ul class="legend" aria-hidden="true">
      <li><span class="mk mk-builtin"></span>{{ t('optimiser.builtin') }}</li>
      <li><span class="mk mk-cuopt"></span>{{ t('optimiser.cuopt') }}</li>
      <li><span class="mk-target"></span>{{ t('chart.target') }}</li>
    </ul>
    <div class="axis" aria-hidden="true">
      <span class="lab"></span>
      <span class="scale"><span v-for="tk in ticks" :key="tk.at" class="tick" :style="{ left: tk.at + '%' }">{{ tk.label }}</span></span>
    </div>
    <ul class="rows">
      <li v-for="(r, i) in rows" :key="r.wo_id" class="row" tabindex="0" :aria-label="describe(r)"
          @mouseenter="hover = i" @mouseleave="hover = null" @focus="hover = i" @blur="hover = null">
        <span class="lab"><span class="mono">{{ r.wo_id.replace(/^WO-\d{8}-/, 'WO-') }}</span><small>{{ r.product_name }}</small></span>
        <span class="track">
          <span v-for="tk in ticks" :key="tk.at" class="grid" :style="{ left: tk.at + '%' }"></span>
          <span v-if="pos(r.target) != null" class="target" :style="{ left: pos(r.target) + '%' }"></span>
          <span v-if="span(r)" class="link" :style="{ left: span(r).left + '%', width: span(r).width + '%' }"></span>
          <span v-if="pos(r.builtin_finish) != null" :class="['mk', 'mk-builtin', { dim: hover !== null && hover !== i }]" :style="{ left: pos(r.builtin_finish) + '%' }"></span>
          <span v-if="pos(r.cuopt_finish) != null" :class="['mk', 'mk-cuopt', { dim: hover !== null && hover !== i }]" :style="{ left: pos(r.cuopt_finish) + '%' }"></span>
        </span>
        <span v-if="hover === i" class="tip" role="status">
          <strong>{{ r.wo_id }} · {{ r.product_name }}</strong>
          <span><span class="mk mk-builtin inline"></span>{{ t('optimiser.builtin') }}: {{ fmtDateTime(r.builtin_finish) }}<template v-if="r.builtin_late"> · {{ t('plan.lateRisk') }}</template></span>
          <span><span class="mk mk-cuopt inline"></span>{{ t('optimiser.cuopt') }}: {{ fmtDateTime(r.cuopt_finish) }}<template v-if="r.cuopt_late"> · {{ t('plan.lateRisk') }}</template></span>
          <span class="muted">{{ t('chart.target') }}: {{ fmtDateTime(r.target) }}</span>
          <span v-if="delta(r)"><strong>{{ delta(r) < 0 ? t('compare.earlier') : t('compare.later') }} {{ Math.abs(delta(r)) }} h</strong> {{ t('chart.withCuopt') }}</span>
        </span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.dumbbell { display: grid; gap: 8px; }
.legend { list-style: none; margin: 0; padding: 0; display: flex; gap: 18px; flex-wrap: wrap; font-size: var(--text-sm); color: var(--ink-2); }
.legend li { display: inline-flex; align-items: center; gap: 8px; }
.axis, .row { display: grid; grid-template-columns: var(--label-w) 1fr; gap: 12px; align-items: center; }
.scale { position: relative; height: 18px; }
.tick { position: absolute; transform: translateX(-50%); font-size: 0.75rem; color: var(--ink-2); white-space: nowrap; font-variant-numeric: tabular-nums; }
.rows { list-style: none; margin: 0; padding: 0; display: grid; }
.row { position: relative; min-height: 40px; outline: none; border-top: 1px solid var(--line); }
.row:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; border-radius: 6px; }
.lab { display: grid; line-height: 1.2; font-size: var(--text-sm); color: var(--ink); min-width: 0; }
.lab small { color: var(--ink-2); font-size: 0.75rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.track { position: relative; height: 40px; }
.grid { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--chart-grid); }
.target { position: absolute; top: 10px; bottom: 10px; width: 2px; margin-left: -1px; background: var(--chart-ref); border-radius: 1px; }
.link { position: absolute; top: 19px; height: 2px; background: var(--line-strong); }
.mk { position: absolute; top: 50%; width: 12px; height: 12px; transform: translate(-50%, -50%); box-shadow: 0 0 0 2px var(--surface); transition: opacity 0.12s; }
.mk-builtin { background: var(--chart-builtin); border-radius: 50%; }
.mk-cuopt { background: var(--chart-1); transform: translate(-50%, -50%) rotate(45deg); width: 11px; height: 11px; border-radius: 2px; }
.legend .mk, .mk.inline { position: static; display: inline-block; transform: none; flex: none; }
.legend .mk-cuopt, .mk-cuopt.inline { transform: rotate(45deg); }
.mk.inline { margin-right: 6px; vertical-align: -1px; }
.mk-target { display: inline-block; width: 2px; height: 14px; background: var(--chart-ref); border-radius: 1px; }
.dim { opacity: 0.35; }
.tip { position: absolute; z-index: 5; left: calc(var(--label-w) + 12px); top: 100%; margin-top: 2px; pointer-events: none;
       display: grid; gap: 3px; background: var(--surface); color: var(--ink); border: 1px solid var(--line-strong);
       border-radius: 10px; padding: 8px 12px; font-size: 0.875rem; box-shadow: 0 6px 20px rgb(0 0 0 / 0.12); min-width: 240px; }
@media (max-width: 560px) {
  .axis, .row { grid-template-columns: 1fr; gap: 2px; }
  .axis .lab { display: none; }
  .tip { left: 0; }
}
@media (prefers-reduced-motion: reduce) { .mk { transition: none; } }
</style>
