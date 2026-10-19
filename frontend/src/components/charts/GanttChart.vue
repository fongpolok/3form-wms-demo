<script setup>
// Plan as a Gantt chart: one row per workstation, time left -> right.
// Encoding (legend below the chart): planned block = de-emphasis blue; the
// selected order = accent blue; changeover = striped; frozen = solid top bar;
// a late-risk order gets a "!" in its label (status never colour-only);
// non-working time (nights, breaks, holidays) = shaded background.
import { computed, ref } from 'vue'
import { appLocale, fmtDateTime, pick } from '../../i18n/index.js'

const props = defineProps({
  plan: { type: Object, required: true },
  hours: { type: Number, default: 72 },              // visible window length
  selected: { type: String, default: null },          // wo_id
  lateIds: { type: Array, default: () => [] },
  stationNames: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['select'])

const PX_PER_HOUR = computed(() => Math.max(14, Math.round(1100 / props.hours)))
const t0 = computed(() => new Date(props.plan.horizon_start).getTime())
const t1 = computed(() => t0.value + props.hours * 3600e3)
const width = computed(() => props.hours * PX_PER_HOUR.value)
const x = (t) => ((new Date(t).getTime() - t0.value) / 3600e3) * PX_PER_HOUR.value
const inView = (a, b) => new Date(b).getTime() > t0.value && new Date(a).getTime() < t1.value

const stations = computed(() => props.plan.stations || [])
const opsBy = computed(() => {
  const m = {}
  for (const op of props.plan.ops || []) if (inView(op.setup_start || op.start, op.end)) (m[op.workstation] ||= []).push(op)
  return m
})
const offTime = computed(() => {   // gaps between working windows inside the view
  const w = (props.plan.working || []).filter((x) => inView(x.start, x.end))
  const out = []
  let cursor = t0.value
  for (const win of w) {
    const s = new Date(win.start).getTime()
    if (s > cursor) out.push([cursor, s])
    cursor = Math.max(cursor, new Date(win.end).getTime())
  }
  if (cursor < t1.value) out.push([cursor, t1.value])
  return out
})
const ticks = computed(() => {
  const step = props.hours <= 24 ? 2 : props.hours <= 72 ? 6 : 24
  const out = []
  const first = Math.ceil(t0.value / (step * 3600e3)) * step * 3600e3
  for (let t = first; t < t1.value; t += step * 3600e3) out.push(t)
  return out
})
const tickLabel = (t) => {
  const d = new Date(t)
  return d.getHours() === 0 || props.hours > 72
    ? d.toLocaleDateString(appLocale(), { weekday: 'short', day: 'numeric', month: 'short' })
    : d.toLocaleTimeString(appLocale(), { hour: '2-digit', minute: '2-digit', hour12: false })
}
const now = Date.now()
const hover = ref(null)
const tip = ref({ x: 0, y: 0 })
function enter(op, e) {
  hover.value = op
  const box = e.currentTarget.closest('.scroll').getBoundingClientRect()
  tip.value = { x: e.clientX - box.left + 12, y: e.clientY - box.top + 14 }
}
const late = computed(() => new Set(props.lateIds))
</script>

<template>
  <div class="gantt">
    <div class="names">
      <div class="axis-space"></div>
      <div v-for="s in stations" :key="s.code" class="name"><strong>{{ s.code }}</strong><span class="muted">{{ pick(stationNames[s.code]) || s.step_code }}</span></div>
    </div>
    <div class="scroll" role="img" :aria-label="`Plan ${plan.plan_id}: ${(plan.ops || []).length} operations`">
      <div class="canvas" :style="{ width: width + 'px' }">
        <div class="axis">
          <span v-for="t in ticks" :key="t" class="tick" :style="{ left: x(t) + 'px' }">{{ tickLabel(t) }}</span>
        </div>
        <div class="rows">
          <div v-for="[a, b] in offTime" :key="a" class="off" :style="{ left: x(a) + 'px', width: x(b) - x(a) + 'px' }"></div>
          <div v-for="t in ticks" :key="'g' + t" class="grid" :style="{ left: x(t) + 'px' }"></div>
          <div v-if="now > t0 && now < t1" class="now" :style="{ left: x(now) + 'px' }"><span>Now</span></div>
          <div v-if="plan.frozen_until && inView(plan.horizon_start, plan.frozen_until)" class="frozen-line"
               :style="{ left: x(plan.frozen_until) + 'px' }"><span>Frozen</span></div>
          <div v-for="s in stations" :key="s.code" class="row">
            <template v-for="op in opsBy[s.code] || []" :key="op.batch_id + op.step_no">
              <div v-if="op.setup_minutes" class="setup" :style="{ left: x(op.setup_start) + 'px', width: Math.max(2, x(op.start) - x(op.setup_start)) + 'px' }"></div>
              <button type="button" :class="['op', { sel: selected === op.wo_id, dim: selected && selected !== op.wo_id, frozen: op.kind !== 'planned' }]"
                      :style="{ left: x(op.start) + 'px', width: Math.max(4, x(op.end) - x(op.start) - 2) + 'px' }"
                      @mouseenter="enter(op, $event)" @mouseleave="hover = null" @focus="hover = op" @blur="hover = null"
                      @click="emit('select', selected === op.wo_id ? null : op.wo_id)"
                      :aria-label="`${op.wo_id} ${op.batch_id} ${op.step_code} ${fmtDateTime(op.start)}`">
                <span v-if="x(op.end) - x(op.start) > 58" class="lbl">{{ late.has(op.wo_id) ? '! ' : '' }}{{ op.product_code }}</span>
              </button>
            </template>
          </div>
        </div>
      </div>
      <div v-if="hover" class="tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }" role="status">
        <strong>{{ hover.wo_id }}</strong> <span v-if="late.has(hover.wo_id)" class="warn">LATE RISK</span>
        <div class="mono">{{ hover.batch_id }} · {{ hover.step_code }} · {{ hover.workstation }}</div>
        <div>{{ fmtDateTime(hover.start) }} → {{ fmtDateTime(hover.end) }}</div>
        <div v-if="hover.setup_minutes" class="muted">+ {{ hover.setup_minutes }} min changeover</div>
        <div class="muted">{{ hover.kind === 'running' ? 'Running now' : hover.kind === 'frozen' ? 'Frozen (will not move)' : 'Planned' }}</div>
      </div>
    </div>
  </div>
  <ul class="legend">
    <li><span class="sw sw-op"></span> Planned</li>
    <li><span class="sw sw-sel"></span> Selected order</li>
    <li><span class="sw sw-setup"></span> Changeover</li>
    <li><span class="sw sw-frozen"></span> Running / frozen</li>
    <li><span class="sw sw-off"></span> Not working (night, break, holiday)</li>
    <li><strong>!</strong> Late-risk order</li>
  </ul>
</template>

<style scoped>
.gantt { display: grid; grid-template-columns: 132px 1fr; border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }
.names { border-right: 1px solid var(--line); background: var(--surface); }
.axis-space { height: 32px; border-bottom: 1px solid var(--line); }
.name { height: 48px; display: grid; align-content: center; padding: 0 12px; border-bottom: 1px solid var(--line); line-height: 1.2; }
.name span { font-size: 0.8125rem; }
.scroll { position: relative; overflow-x: auto; }
.canvas { position: relative; }
.axis { position: relative; height: 32px; border-bottom: 1px solid var(--line); }
.tick { position: absolute; top: 8px; transform: translateX(-50%); font-size: 0.8125rem; color: var(--ink-2); white-space: nowrap; }
.rows { position: relative; }
.row { position: relative; height: 48px; border-bottom: 1px solid var(--line); }
.off { position: absolute; top: 0; bottom: 0; background: var(--chart-off); }
.grid { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--chart-grid); }
.now, .frozen-line { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--alarm); z-index: 3; }
.frozen-line { background: var(--ink-2); width: 1px; }
.now span, .frozen-line span { position: absolute; top: 2px; left: 4px; font-size: 0.75rem; font-weight: 700; color: var(--ink-2); background: var(--surface); padding: 0 3px; border-radius: 3px; }
.now span { color: var(--alarm); }
.op { position: absolute; top: 10px; height: 28px; border: 0; padding: 0 6px; border-radius: 4px; cursor: pointer; z-index: 2;
      background: var(--chart-2); color: var(--chart-2-text); text-align: left; overflow: hidden; }
.op.sel { background: var(--chart-1); color: var(--chart-1-text); }
.op.dim { opacity: 0.35; }
.op.frozen { box-shadow: inset 0 4px 0 var(--ink); }
.lbl { font: 650 0.75rem/28px var(--font-body); white-space: nowrap; }
.setup { position: absolute; top: 10px; height: 28px; border-radius: 4px 0 0 4px; z-index: 1;
         background: repeating-linear-gradient(45deg, var(--chart-2) 0 3px, transparent 3px 7px); opacity: 0.7; }
.tip { position: absolute; z-index: 10; pointer-events: none; display: grid; gap: 2px; background: var(--surface); color: var(--ink);
       border: 1px solid var(--line-strong); border-radius: 10px; padding: 8px 12px; font-size: 0.875rem; box-shadow: 0 6px 20px rgb(0 0 0 / 0.12); white-space: nowrap; }
.warn { color: var(--alarm); font-weight: 700; }
.legend { list-style: none; display: flex; flex-wrap: wrap; gap: 16px; padding: 0; margin: 12px 0 0; font-size: var(--text-sm); color: var(--ink-2); }
.legend li { display: flex; align-items: center; gap: 6px; }
.sw { width: 18px; height: 12px; border-radius: 3px; display: inline-block; }
.sw-op { background: var(--chart-2); }
.sw-sel { background: var(--chart-1); }
.sw-setup { background: repeating-linear-gradient(45deg, var(--chart-2) 0 3px, transparent 3px 7px); border: 1px solid var(--line); }
.sw-frozen { background: var(--chart-2); box-shadow: inset 0 4px 0 var(--ink); }
.sw-off { background: var(--chart-off); border: 1px solid var(--line); }
</style>
