<script setup>
// PIC registers workstation tablets. "Register this device" stores the token on
// this browser (then open /worker). For another tablet, the one-time code is
// typed into that tablet's worker screen.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, patch, post } from '../../api/client.js'
import { usePolled } from '../../composables/poll.js'
import { storage } from '../../composables/storage.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'

const { t } = useI18n()
const { data, error, reload } = usePolled(() => get('/api/v1/devices'), 0)
const stations = usePolled(() => get('/api/v1/mes/workstations'), 0).data
const form = ref({ name: '', workstation: 'WS-01' })
const msg = ref({ text: '', kind: 'ok' })
const oneTimeCode = ref('')

async function register(thisDevice) {
  oneTimeCode.value = ''
  try {
    const res = await post('/api/v1/devices', form.value)
    if (thisDevice) {
      storage.local.set('deviceToken', res.device_token)
      msg.value = { text: t('devices.tokenOnce', { ws: res.device.workstation }), kind: 'ok' }
    } else {
      oneTimeCode.value = res.device_token
      msg.value = { text: '', kind: 'ok' }
    }
    form.value.name = ''
    reload()
  } catch (e) { msg.value = { text: e.message, kind: 'error' } }
}
async function toggle(d) {
  try { await patch(`/api/v1/devices/${d.id}`, { is_active: !d.is_active }); reload() } catch (e) { msg.value = { text: e.message, kind: 'error' } }
}
</script>

<template>
  <PageHead :title="t('devices.title')" :subtitle="t('devices.subtitle')" />
  <form class="card form" @submit.prevent>
    <h2 class="full">{{ t('devices.register') }}</h2>
    <label class="field"><span>{{ t('devices.name') }}</span><input v-model="form.name" required placeholder="Tablet – Filling" /></label>
    <label class="field"><span>{{ t('devices.workstation') }}</span>
      <select v-model="form.workstation"><option v-for="w in stations" :key="w.code" :value="w.code">{{ w.code }} · {{ w.step_code }}</option></select></label>
    <div class="row full">
      <button class="btn btn-primary" :disabled="!form.name" @click="register(true)"><Icon name="tablet" :size="18" /> {{ t('devices.registerThis') }}</button>
      <button class="btn" :disabled="!form.name" @click="register(false)">{{ t('devices.register') }}</button>
      <RouterLink v-if="msg.kind === 'ok' && msg.text" to="/worker" class="btn">/worker →</RouterLink>
    </div>
    <p v-if="msg.text" :class="['notice full', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>
    <div v-if="oneTimeCode" class="notice notice-ok full">
      <p>{{ t('devices.otherDevice') }}</p><p class="mono code">{{ oneTimeCode }}</p>
    </div>
  </form>
  <p v-if="error" class="notice notice-error">{{ error }}</p>
  <div class="card table-wrap block">
    <table class="table">
      <thead><tr><th>{{ t('devices.name') }}</th><th>{{ t('devices.workstation') }}</th><th>ID</th><th>{{ t('devices.lastSeen') }}</th><th>{{ t('common.status') }}</th><th></th></tr></thead>
      <tbody>
        <tr v-for="d in data" :key="d.id">
          <td>{{ d.name }}</td><td>{{ d.workstation }}</td><td class="mono">{{ d.token_hint }}…</td>
          <td>{{ d.last_seen ? new Date(d.last_seen).toLocaleString() : '–' }}</td>
          <td><span :class="['pill', d.is_active ? 'pill-ok' : 'pill-alarm']"><Icon :name="d.is_active ? 'check' : 'x'" :size="12" /> {{ d.is_active ? t('accounts.active') : t('devices.revoke') }}</span></td>
          <td><button class="btn" @click="toggle(d)">{{ d.is_active ? t('devices.revoke') : t('devices.activate') }}</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.form { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
.full { grid-column: 1 / -1; }
.block { margin-top: 20px; }
.code { font-size: 1.125rem; word-break: break-all; margin-top: 6px; user-select: all; }
</style>
