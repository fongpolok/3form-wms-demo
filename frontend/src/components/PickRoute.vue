<script setup>
// An ordered pick list: walk to the bins in this order (built-in or NVIDIA cuOpt route).
import { useI18n } from 'vue-i18n'

defineProps({ route: { type: Object, required: true } })
const { t } = useI18n()
const fmtLines = (lines) => lines.map((l) => `${l.goods_code} · ${l.lot_number || '–'} × ${l.qty.toLocaleString()}`).join('; ')
</script>

<template>
  <section class="stack pick" :aria-label="t('pick.title')">
    <div class="row">
      <h3 class="grow">{{ t('pick.title') }}</h3>
      <span class="pill pill-info">{{ t('pick.engine') }}: {{ route.engine === 'cuopt' ? t('optimiser.cuopt') : t('optimiser.builtin') }}</span>
      <span class="pill">{{ t('pick.distance') }}: {{ route.distance_m }} m</span>
    </div>
    <p class="muted small">{{ t('pick.depot', route.depot) }}</p>
    <p v-for="s in route.shortages" :key="s.goods_code" class="notice notice-error small">{{ t('pick.short') }}: {{ s.goods_code }} (−{{ s.short_by }})</p>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>{{ t('pick.stop') }}</th><th>{{ t('pick.bin') }}</th><th>{{ t('pick.where') }}</th><th>{{ t('pick.items') }}</th></tr></thead>
        <tbody>
          <tr v-for="s in route.stops" :key="s.bin_name"><td><strong>{{ s.seq }}</strong></td><td class="mono">{{ s.bin_name }}</td>
            <td class="mono">{{ s.aisle }} · {{ s.position }}</td><td class="mono">{{ fmtLines(s.lines) }}</td></tr>
          <tr v-for="s in route.unlocated" :key="s.bin_name" class="unlocated"><td>?</td><td class="mono">{{ s.bin_name }}</td>
            <td>{{ t('pick.unlocated') }}</td><td class="mono">{{ fmtLines(s.lines) }}</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.pick { background: var(--surface-2); border-radius: var(--radius); padding: 12px 16px; }
.pick h3 { margin: 0; font-size: var(--text-md, 1rem); }
.grow { flex: 1; }
.small { font-size: var(--text-sm); margin: 0; }
.unlocated td { color: var(--ink-2); }
</style>
