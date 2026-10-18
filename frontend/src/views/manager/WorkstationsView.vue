<script setup>
import { useI18n } from 'vue-i18n'
import { get } from '../../api/client.js'
import { pick } from '../../i18n/index.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'

const { t } = useI18n()
const { data, error } = usePolled(() => get('/api/v1/mes/station-status'), 5000)

function state(ws) {
  if (ws.devices.some((d) => !d.ok)) return { cls: 'pill-alarm', icon: 'wifi', text: t('alarm.title') }
  if (ws.running?.machine_stopped) return { cls: 'pill-alarm', icon: 'pause', text: t('worker.machineStopped') }
  if (ws.running) return { cls: 'pill-ok', icon: 'play', text: t('progress.running') }
  return { cls: 'pill-info', icon: 'station', text: t('progress.waiting') }
}
</script>

<template>
  <PageHead :title="t('nav.workstations')" />
  <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
  <div class="grid">
    <article v-for="ws in data" :key="ws.code" class="card stack">
      <div class="row">
        <div class="grow">
          <p class="muted mono">{{ ws.code }}</p>
          <h2>{{ pick(ws.step_name) }}</h2>
        </div>
        <span :class="['pill', state(ws).cls]"><Icon :name="state(ws).icon" :size="14" /> {{ state(ws).text }}</span>
      </div>
      <div v-if="ws.running">
        <p class="mono">{{ ws.running.batch_id }}</p>
        <p class="muted">#{{ ws.running.started_by }}<template v-if="ws.running.stop_reason"> · {{ ws.running.stop_reason }}</template></p>
      </div>
      <ul class="devs">
        <li v-for="d in ws.devices" :key="d.device_id">
          <Icon :name="d.ok ? 'check' : 'x'" :size="16" /> {{ d.device_id }}
          <span class="muted">{{ d.ok ? t('common.online') : t('common.offline') }}<template v-if="d.seconds_since_seen != null"> · {{ d.seconds_since_seen }}s</template></span>
        </li>
        <li v-if="!ws.devices.length" class="muted">No scanner configured</li>
      </ul>
    </article>
  </div>
</template>

<style scoped>
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.grow { flex: 1; }
.devs { list-style: none; padding: 0; margin: 0; display: grid; gap: 4px; font-size: var(--text-sm); }
.devs li { display: flex; gap: 6px; align-items: center; }
</style>
