<script setup>
// Horizontal bars from one baseline, drawn with HTML so text stays at real
// size in narrow cards. Single series => no legend (the frame title names it).
// Bars 20px thick with a 4px rounded data-end (square at the baseline), value
// at the tip in text ink, hover/focus tooltip.
import { computed, ref } from 'vue'

const props = defineProps({
  items: { type: Array, required: true },   // [{ key, label, value, valueLabel?, emphasis?: bool, tip?: string[] }]
  max: { type: Number, default: null },
  unit: { type: String, default: '' },
  labelWidth: { type: Number, default: 130 },
})
const top = computed(() => props.max ?? Math.max(1, ...props.items.map((i) => i.value || 0)))
const hover = ref(null)
const pct = (v) => (v == null ? 0 : Math.max(0.5, (v / top.value) * 100))
</script>

<template>
  <ul class="bars" :style="{ '--label-w': labelWidth + 'px' }">
    <li v-for="(it, i) in items" :key="it.key" class="row" tabindex="0"
        @mouseenter="hover = i" @mouseleave="hover = null" @focus="hover = i" @blur="hover = null"
        :aria-label="`${it.label}: ${it.valueLabel ?? it.value + unit}`">
      <span class="lab">{{ it.label }}</span>
      <span class="track">
        <span v-if="it.value != null" :class="['bar', it.emphasis === false ? 'bar-2' : 'bar-1', { dim: hover !== null && hover !== i }]"
              :style="{ width: `calc(${pct(it.value)}% - 72px * ${pct(it.value) / 100})` }"></span>
        <span class="val">{{ it.value == null ? '–' : (it.valueLabel ?? `${it.value}${unit}`) }}</span>
      </span>
      <span v-if="hover === i && it.tip" class="tip" role="status">
        <strong>{{ it.label }}</strong><span v-for="line in it.tip" :key="line">{{ line }}</span>
      </span>
    </li>
  </ul>
</template>

<style scoped>
.bars { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.row { position: relative; display: grid; grid-template-columns: var(--label-w) 1fr; align-items: center; gap: 10px; outline: none; }
.row:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; border-radius: 6px; }
.lab { font-size: var(--text-sm); color: var(--ink-2); text-align: right; overflow-wrap: anywhere; line-height: 1.2; }
.track { display: flex; align-items: center; gap: 8px; min-width: 0; border-left: 1px solid var(--chart-grid); min-height: 28px; }
.bar { display: block; height: 20px; border-radius: 0 4px 4px 0; transition: opacity 0.12s; }
.bar-1 { background: var(--chart-1); }
.bar-2 { background: var(--chart-2); }
.dim { opacity: 0.45; }
.val { font-size: var(--text-sm); font-weight: 650; color: var(--ink); white-space: nowrap; font-variant-numeric: tabular-nums; }
.tip { position: absolute; z-index: 5; left: calc(var(--label-w) + 24px); top: 100%; margin-top: 4px; pointer-events: none;
       display: grid; gap: 2px; background: var(--surface); color: var(--ink); border: 1px solid var(--line-strong);
       border-radius: 10px; padding: 8px 12px; font-size: 0.875rem; box-shadow: 0 6px 20px rgb(0 0 0 / 0.12); min-width: 180px; }
@media (max-width: 520px) { .row { grid-template-columns: 1fr; gap: 4px; } .lab { text-align: left; } }
</style>
