<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, patch, post } from '../../api/client.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'

const { t } = useI18n()
const { data, error, reload } = usePolled(() => get('/api/v1/accounts'), 0)
const blank = () => ({ display_name: '', staff_id: '', role: 'WORKER', username: '', password: '' })
const form = ref(blank())
const msg = ref({ text: '', kind: 'ok' })

async function add() {
  try {
    await post('/api/v1/accounts', form.value)
    msg.value = { text: `${form.value.display_name} ✓`, kind: 'ok' }
    form.value = blank(); reload()
  } catch (e) { msg.value = { text: e.message, kind: 'error' } }
}
async function update(a, body) {
  try { await patch(`/api/v1/accounts/${a.id}`, body); reload() } catch (e) { msg.value = { text: e.message, kind: 'error' } }
}
</script>

<template>
  <PageHead :title="t('accounts.title')" />
  <form class="card form" @submit.prevent="add">
    <h2 class="full">{{ t('accounts.add') }}</h2>
    <label class="field"><span>{{ t('accounts.name') }}</span><input v-model="form.display_name" required /></label>
    <label class="field"><span>{{ t('accounts.staffId') }}</span><input v-model="form.staff_id" required /></label>
    <label class="field"><span>{{ t('accounts.role') }}</span>
      <select v-model="form.role"><option value="WORKER">{{ t('role.WORKER') }}</option><option value="EM">{{ t('role.EM') }}</option><option value="PIC">{{ t('role.PIC') }}</option></select></label>
    <template v-if="form.role !== 'WORKER'">
      <label class="field"><span>{{ t('accounts.username') }}</span><input v-model="form.username" autocomplete="off" required /></label>
      <label class="field"><span>{{ t('accounts.password') }}</span><input v-model="form.password" type="password" autocomplete="new-password" required /></label>
    </template>
    <div class="row full">
      <button class="btn btn-primary">{{ t('accounts.add') }}</button>
      <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>
    </div>
  </form>
  <p v-if="error" class="notice notice-error">{{ error }}</p>
  <div class="card table-wrap block">
    <table class="table">
      <thead><tr><th>{{ t('accounts.name') }}</th><th>{{ t('accounts.staffId') }}</th><th>{{ t('accounts.role') }}</th>
        <th>{{ t('accounts.username') }}</th><th>{{ t('common.status') }}</th><th>{{ t('common.actions') }}</th></tr></thead>
      <tbody>
        <tr v-for="a in data" :key="a.id">
          <td>{{ a.display_name }}</td><td class="mono">{{ a.staff_id }}</td><td>{{ t(`role.${a.role}`) }}</td><td>{{ a.username || '–' }}</td>
          <td>
            <span v-if="a.is_locked" class="pill pill-alarm"><Icon name="alert" :size="12" /> {{ t('accounts.locked') }}</span>
            <span v-else-if="a.is_active" class="pill pill-ok"><Icon name="check" :size="12" /> {{ t('accounts.active') }}</span>
            <span v-else class="pill pill-warn"><Icon name="x" :size="12" /> {{ t('accounts.disable') }}</span>
          </td>
          <td class="row">
            <button v-if="a.is_locked" class="btn" @click="update(a, { unlock: true })">{{ t('accounts.unlock') }}</button>
            <button class="btn" @click="update(a, { is_active: !a.is_active })">{{ a.is_active ? t('accounts.disable') : t('accounts.enable') }}</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.form { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.full { grid-column: 1 / -1; }
.block { margin-top: 20px; }
</style>
