<script setup>
// The progress bar drawn as the real production line:
//   Order → step 1 → step 2 → … → To stock / Ship to client
// Each station shows how many batches have passed it, and which are there now.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { pick } from '../i18n/index.js'
import Icon from './Icon.vue'

const props = defineProps({ wo: { type: Object, required: true } })
const { t } = useI18n()

const stations = computed(() => {
  const batches = props.wo.batches || []
  const n = batches.length || 1
  const steps = (props.wo.routing || []).map((s) => {
    const finished = (b) => b.status === 'done' || b.status === 'awaiting_putaway'
    const passed = batches.filter((b) => finished(b) || b.current_step_no > s.step_no).length
    const here = batches.filter((b) => !finished(b) && b.current_step_no === s.step_no)
    return {
      key: s.code, label: pick(s.name), passed, total: n,
      running: here.filter((b) => b.status === 'running').length,
      waiting: here.filter((b) => b.status === 'waiting').length,
    }
  })
  const done = batches.filter((b) => b.status === 'done').length
  return [
    { key: 'order', label: t('progress.order'), passed: n, total: n, running: 0, waiting: 0 },
    ...steps,
    { key: 'end', label: props.wo.ship_mode === 'stock' ? t('progress.toStock') : t('progress.toClient'),
      passed: done, total: n, running: 0, waiting: 0, end: true },
  ]
})

function stateOf(s) {
  if (s.passed === s.total) return 'done'
  if (s.running) return 'running'
  if (s.waiting || s.passed > 0) return 'partial'
  return 'todo'
}
</script>

<template>
  <div class="rail" role="progressbar" :aria-valuenow="wo.progress_pct" aria-valuemin="0" aria-valuemax="100"
       :aria-label="`${wo.wo_id}: ${wo.progress_pct}%`">
    <ol class="stations">
      <li v-for="(s, i) in stations" :key="s.key" :class="['st', stateOf(s), { end: s.end }]">
        <span class="track" v-if="i > 0" :class="{ lit: stations[i - 1].passed > 0 }" aria-hidden="true"></span>
        <span class="node" aria-hidden="true">
          <Icon v-if="stateOf(s) === 'done'" name="check" :size="16" />
          <Icon v-else-if="stateOf(s) === 'running'" name="play" :size="14" />
        </span>
        <span class="label">{{ s.label }}</span>
        <span class="count" v-if="s.total > 1 || s.running || s.waiting">
          {{ s.passed }}/{{ s.total }}
          <template v-if="s.running"> · {{ t('progress.running') }}</template>
        </span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.rail { overflow-x: auto; padding: 4px 2px 2px; }
.stations { list-style: none; margin: 0; padding: 0; display: flex; min-width: max-content; }
.st { position: relative; display: grid; justify-items: center; align-content: start; gap: 6px; min-width: 92px; padding-top: 2px; }
.track { position: absolute; top: 15px; right: 50%; width: 100%; height: 4px; background: var(--line); z-index: 0; }
.track.lit { background: var(--accent); }
.node {
  position: relative; z-index: 1; width: 30px; height: 30px; border-radius: 50%;
  display: grid; place-items: center; border: 3px solid var(--line-strong); background: var(--surface); color: var(--accent-ink);
}
.done .node { background: var(--accent); border-color: var(--accent); }
.running .node { border-color: var(--accent); color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); }
.partial .node { border-color: var(--accent); background: linear-gradient(90deg, var(--accent) 50%, var(--surface) 50%); }
.end .node { border-radius: 8px; }
.label { font-size: var(--text-sm); font-weight: 600; text-align: center; max-width: 110px; }
.todo .label { color: var(--ink-2); font-weight: 500; }
.count { font-size: 0.8125rem; color: var(--ink-2); }
</style>
