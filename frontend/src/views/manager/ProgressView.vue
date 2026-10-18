<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { get } from '../../api/client.js'
import { usePolled } from '../../composables/poll.js'
import LineRail from '../../components/LineRail.vue'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'

const { t } = useI18n()
const { data, error, loading, reload } = usePolled(() => get('/api/v1/mes/progress'), 10000)
const today = new Date().toISOString().slice(0, 10)

const summary = computed(() => {
  const wos = data.value || []
  return {
    running: wos.filter((w) => w.status === 'in_progress').length,
    waiting: wos.filter((w) => w.status === 'released' || w.status === 'waiting_material').length,
    done: wos.filter((w) => w.status === 'done').length,
    late: wos.filter((w) => w.status !== 'done' && w.due_date < today).length,
  }
})
</script>

<template>
  <PageHead :title="t('progress.title')" :subtitle="t('progress.subtitle')">
    <button class="btn" @click="reload">{{ t('common.refresh') }}</button>
  </PageHead>
  <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
  <p v-if="loading" class="muted">{{ t('common.loading') }}</p>

  <div v-if="data" class="summary" role="list">
    <div role="listitem" class="sum"><span class="n">{{ summary.running }}</span><span>{{ t('progress.running') }}</span></div>
    <div role="listitem" class="sum"><span class="n">{{ summary.waiting }}</span><span>{{ t('progress.waiting') }}</span></div>
    <div role="listitem" class="sum"><span class="n">{{ summary.done }}</span><span>{{ t('progress.done') }}</span></div>
    <div role="listitem" class="sum" :class="{ late: summary.late }">
      <span class="n">{{ summary.late }}</span><span><Icon v-if="summary.late" name="alert" :size="16" /> {{ t('progress.late') }}</span>
    </div>
  </div>

  <p v-if="data && !data.length" class="muted">{{ t('common.none') }}</p>
  <div class="stack">
    <article v-for="wo in data" :key="wo.wo_id" class="card wo">
      <div class="row">
        <div class="grow">
          <div class="row tight">
            <h2 class="mono">{{ wo.wo_id }}</h2>
            <span v-if="wo.special_urgent" class="pill pill-alarm"><Icon name="alert" :size="14" /> {{ t('progress.urgent') }}</span>
            <span v-if="wo.status === 'waiting_material'" class="pill pill-warn"><Icon name="alert" :size="14" /> {{ t('wo.waitingMaterial') }}</span>
            <span v-if="wo.status === 'done'" class="pill pill-ok"><Icon name="check" :size="14" /> {{ t('progress.done') }}</span>
            <span v-else-if="wo.due_date < today" class="pill pill-warn"><Icon name="alert" :size="14" /> {{ t('progress.late') }}</span>
          </div>
          <p class="muted">{{ wo.product_name || wo.product_code }} · {{ wo.client }} · {{ wo.qty }} pcs ·
            {{ wo.batches.length }} {{ t('progress.batches') }} · {{ t('progress.due') }} {{ wo.due_date }}</p>
        </div>
        <div class="pct" aria-hidden="true">{{ Math.round(wo.progress_pct) }}<small>%</small></div>
      </div>
      <LineRail :wo="wo" />
    </article>
  </div>
</template>

<style scoped>
.summary { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; margin-bottom: 20px; }
.sum { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-lg); padding: 14px 18px; display: grid; }
.sum .n { font-size: 1.75rem; font-weight: 700; }
.sum span:last-child { color: var(--ink-2); font-size: var(--text-sm); display: inline-flex; gap: 4px; align-items: center; }
.sum.late { border-color: var(--warn); }
.sum.late .n { color: var(--warn); }
.wo h2 { font-size: var(--text-lg); }
.tight { gap: 8px; }
.grow { flex: 1; min-width: 0; }
.pct { font-size: 2rem; font-weight: 700; color: var(--accent); }
.pct small { font-size: 1rem; }
.wo { display: grid; gap: 16px; }
@media (max-width: 640px) { .summary { grid-template-columns: repeat(2, 1fr); } }
</style>
