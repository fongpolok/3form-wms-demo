<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, post } from '../../api/client.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'

const { t } = useI18n()
const showClosed = ref(false)
const { data, reload } = usePolled(() => get(`/api/v1/alerts?open=${showClosed.value ? 0 : 1}`), 15000)
async function ack(a) { await post(`/api/v1/alerts/${a.id}/ack`, {}); reload() }
const sev = { alarm: ['pill-alarm', 'alert'], warn: ['pill-warn', 'alert'], info: ['pill-info', 'check'] }
</script>

<template>
  <PageHead :title="t('nav.alerts')" :subtitle="t('alerts.subtitle')">
    <label class="chk"><input type="checkbox" v-model="showClosed" @change="reload" /> {{ t('alerts.showClosed') }}</label>
  </PageHead>
  <p v-if="data && !data.length" class="muted">{{ t('alerts.none') }}</p>
  <div class="stack">
    <article v-for="a in data" :key="a.id" class="card row alert">
      <span :class="['pill', sev[a.severity][0]]"><Icon :name="sev[a.severity][1]" :size="14" /> {{ t(`alerts.kind.${a.kind}`) }}</span>
      <div class="grow"><strong>{{ a.title }}</strong><p class="muted">{{ a.detail }}</p>
        <p class="muted small">{{ $dt(a.created_at) }}<template v-if="a.acknowledged_by"> · ✓ {{ a.acknowledged_by }}</template></p></div>
      <button v-if="a.is_open" class="btn" @click="ack(a)">{{ t('alerts.ack') }}</button>
    </article>
  </div>
</template>

<style scoped>
.alert { align-items: flex-start; }
.grow { flex: 1; min-width: 0; }
.small { font-size: 0.8125rem; margin-top: 4px; }
.chk { display: flex; gap: 6px; align-items: center; }
.chk input { width: auto; min-height: auto; }
</style>
