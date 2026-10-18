<script setup>
import { fmtDateTime } from '../../i18n/index.js'
// Individuals (I) chart: one 2px series line, reference lines for centre,
// control limits (UCL/LCL) and spec limits (USL/LSL), each labelled at the right
// edge (no legend colours to match). Rule breaks: alarm-colour dot with a surface
// ring + "!" label. Hover = crosshair + tooltip with the exact reading.
import { computed, ref } from 'vue'

const props = defineProps({ data: { type: Object, required: true } })
const W = 720
const H = 300
const M = { l: 52, r: 112, t: 22, b: 28 }
const hover = ref(null)

const pts = computed(() => props.data.points || [])
const bad = computed(() => new Set((props.data.violations || []).map((v) => v.index)))
const yDomain = computed(() => {
  const vals = pts.value.map((p) => p.value)
  const refs = [props.data.ucl, props.data.lcl, props.data.usl, props.data.lsl].filter((v) => v != null)
  let lo = Math.min(...vals, ...refs)
  let hi = Math.max(...vals, ...refs)
  const pad = (hi - lo || 1) * 0.08
  return [lo - pad, hi + pad]
})
const x = (i) => M.l + (i * (W - M.l - M.r)) / Math.max(1, pts.value.length - 1)
const y = (v) => M.t + ((yDomain.value[1] - v) / (yDomain.value[1] - yDomain.value[0])) * (H - M.t - M.b)
const path = computed(() => pts.value.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' '))
const ticks = computed(() => {
  const [lo, hi] = yDomain.value
  const step = niceStep((hi - lo) / 4)
  const out = []
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(+v.toFixed(3))
  return out
})
function niceStep(raw) {
  const p = 10 ** Math.floor(Math.log10(raw))
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw)
}
const refs = computed(() => {
  const list = [
    { key: 'usl', v: props.data.usl, label: 'USL', cls: 'spec' },
    { key: 'ucl', v: props.data.ucl, label: 'UCL', cls: 'ctrl' },
    { key: 'centre', v: props.data.centre, label: 'Mean', cls: 'centre' },
    { key: 'lcl', v: props.data.lcl, label: 'LCL', cls: 'ctrl' },
    { key: 'lsl', v: props.data.lsl, label: 'LSL', cls: 'spec' },
  ].filter((r) => r.v != null).sort((a, b) => b.v - a.v)
  // Label positions: keep 15px apart so neighbouring reference labels never overlap.
  let last = -Infinity
  for (const r of list) { r.ly = Math.max(y(r.v) + 4, last + 15); last = r.ly }
  return list
})
// One "!" per cluster of nearby rule breaks (the dots stay on every point).
const bangs = computed(() => {
  const out = []
  for (const i of [...bad.value].sort((a, b) => a - b)) {
    if (!out.length || x(i) - x(out[out.length - 1]) > 14) out.push(i)
  }
  return out
})

function move(e) {
  const box = e.currentTarget.getBoundingClientRect()
  const px = ((e.clientX - box.left) / box.width) * W
  const i = Math.round(((px - M.l) / (W - M.l - M.r)) * (pts.value.length - 1))
  hover.value = i >= 0 && i < pts.value.length ? i : null
}
const fmtTime = (ts) => fmtDateTime(ts)
</script>

<template>
  <div class="wrap">
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" @mousemove="move" @mouseleave="hover = null"
         :aria-label="`${data.measure}: ${pts.length} readings, mean ${data.centre}, limits ${data.lcl} to ${data.ucl}, ${bad.size} rule breaks`">
      <g class="grid">
        <line v-for="t in ticks" :key="t" :x1="M.l" :x2="W - M.r" :y1="y(t)" :y2="y(t)" />
        <text v-for="t in ticks" :key="'l' + t" :x="M.l - 8" :y="y(t) + 4" text-anchor="end">{{ t }}</text>
      </g>
      <g v-for="r in refs" :key="r.key" :class="['ref', r.cls]">
        <line :x1="M.l" :x2="W - M.r" :y1="y(r.v)" :y2="y(r.v)" />
        <text :x="W - M.r + 8" :y="r.ly">{{ r.label }} {{ +r.v.toFixed(2) }}</text>
      </g>
      <path :d="path" class="series" />
      <circle v-for="i in [...bad]" :key="'v' + i" :cx="x(i)" :cy="y(pts[i].value)" r="6" class="breach" />
      <text v-for="i in bangs" :key="'b' + i" :x="x(i)" :y="y(pts[i].value) - 11" text-anchor="middle" class="breach-label">!</text>
      <g v-if="hover !== null">
        <line :x1="x(hover)" :x2="x(hover)" :y1="M.t" :y2="H - M.b" class="cross" />
        <circle :cx="x(hover)" :cy="y(pts[hover].value)" r="5" class="dot" />
      </g>
      <text :x="M.l" :y="H - 6" class="axis-note">older</text>
      <text :x="W - M.r" :y="H - 6" text-anchor="end" class="axis-note">latest</text>
    </svg>
    <div v-if="hover !== null" class="tip" :style="{ left: `${(x(hover) / W) * 100}%` }" role="status">
      <strong>{{ pts[hover].value }} {{ data.unit }}</strong>
      <div>{{ fmtTime(pts[hover].ts) }}</div>
      <div class="muted">{{ pts[hover].batch_id }} · {{ pts[hover].workstation }}</div>
      <div v-if="bad.has(hover)" class="warn">Rule break</div>
    </div>
  </div>
</template>

<style scoped>
.wrap { position: relative; }
svg { width: 100%; height: auto; display: block; cursor: crosshair; }
.grid line { stroke: var(--chart-grid); stroke-width: 1; }
.grid text, .axis-note { fill: var(--ink-2); font-size: 13px; font-variant-numeric: tabular-nums; }
.ref line { stroke: var(--chart-ref); stroke-width: 1; }
.ref.ctrl line { stroke-dasharray: 6 4; }
.ref.spec line { stroke-dasharray: 2 4; }
.ref.centre line { stroke-width: 1.5; }
.ref text { fill: var(--ink-2); font-size: 13px; font-weight: 600; }
.series { fill: none; stroke: var(--chart-1); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.breach { fill: var(--alarm); stroke: var(--surface); stroke-width: 2; }
.breach-label { fill: var(--alarm); font-weight: 800; font-size: 13px; }
.cross { stroke: var(--ink-2); stroke-width: 1; }
.dot { fill: var(--chart-1); stroke: var(--surface); stroke-width: 2; }
.tip { position: absolute; top: 8px; transform: translateX(-50%); pointer-events: none; background: var(--surface);
       border: 1px solid var(--line-strong); border-radius: 10px; padding: 8px 12px; font-size: 0.875rem; white-space: nowrap;
       box-shadow: 0 6px 20px rgb(0 0 0 / 0.12); }
.warn { color: var(--alarm); font-weight: 700; }
</style>
