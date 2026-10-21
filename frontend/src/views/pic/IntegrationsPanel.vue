<script setup>
// Settings -> Integrations (PIC only): AI provider, optimiser (built-in / cuOpt), ERP connections, read-only API keys.
// Secrets are write-only: the screen only ever shows the last 4 characters.
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { del, get, post, put } from '../../api/client.js'
import { fmtDateTime } from '../../i18n/index.js'

const { t } = useI18n()
const ai = ref(null)
const aiKey = ref('')
const aiTest = ref('')
const opt = ref(null)
const optToken = ref('')
const optTest = ref('')
const erp = ref({ connections: [], systems: [] })
const erpForm = ref(null)
const keys = ref([])
const keyName = ref('')
const newKey = ref(null)
const msg = ref({ text: '', kind: 'ok' })

const fail = (e) => { msg.value = { kind: 'error', text: e.message } }
const ok = (text) => { msg.value = { kind: 'ok', text } }
async function load() {
  try {
    ;[ai.value, erp.value, keys.value, opt.value] = await Promise.all([get('/api/v1/integrations/ai'), get('/api/v1/integrations/erp'),
      get('/api/v1/integrations/api-keys'), get('/api/v1/integrations/optimiser')])
  } catch (e) { fail(e) }
}
onMounted(load)
async function saveAi() {
  try { ai.value = await put('/api/v1/integrations/ai', { ...ai.value, api_key: aiKey.value || undefined }); aiKey.value = ''; ok(t('integrations.saved')) } catch (e) { fail(e) }
}
async function testAi() { aiTest.value = '…'; try { const r = await post('/api/v1/integrations/ai/test', {}); aiTest.value = r.ok ? `✓ ${r.model}: ${r.reply}` : `✕ ${r.reply}` } catch (e) { aiTest.value = e.message } }
async function saveOpt(clear = false) {
  try {
    const { plan_engine, pick_engine, cuopt_url } = opt.value
    opt.value = await put('/api/v1/integrations/optimiser', { plan_engine, pick_engine, cuopt_url, cuopt_token: optToken.value || undefined, clear_token: clear || undefined })
    optToken.value = ''; ok(t('integrations.saved'))
  } catch (e) { fail(e) }
}
async function testOpt() { optTest.value = '…'; try { const r = await post('/api/v1/integrations/optimiser/test', { cuopt_url: opt.value.cuopt_url }); optTest.value = `${r.ok ? '✓' : '✕'} ${r.reply}` } catch (e) { optTest.value = e.message } }
function editErp(c) { erpForm.value = c ? { ...c, secret: '' } : { name: '', system: 'SAP', base_url: '', auth_type: 'basic', username: '', secret: '', company_code: '', enabled: false } }
async function saveErp() {
  try {
    const body = { ...erpForm.value }
    if (!body.secret) delete body.secret
    if (body.id) await put(`/api/v1/integrations/erp/${body.id}`, body); else await post('/api/v1/integrations/erp', body)
    erpForm.value = null; ok(t('integrations.saved')); load()
  } catch (e) { fail(e) }
}
async function testErp(c) { try { await post(`/api/v1/integrations/erp/${c.id}/test`, {}); load() } catch (e) { fail(e) } }
async function removeErp(c) { if (confirm(t('integrations.confirmRemove', { name: c.name }))) { await del(`/api/v1/integrations/erp/${c.id}`); load() } }
async function createKey() {
  try { newKey.value = await post('/api/v1/integrations/api-keys', { name: keyName.value }); keyName.value = ''; load() } catch (e) { fail(e) }
}
async function revoke(k) { if (confirm(t('integrations.confirmRevoke', { name: k.name }))) { await post(`/api/v1/integrations/api-keys/${k.id}/revoke`, {}); load() } }
</script>

<template>
  <section class="card stack integ">
    <h2>{{ t('integrations.title') }}</h2>
    <p class="muted">{{ t('integrations.subtitle') }}</p>
    <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>

    <!-- AI provider -->
    <div v-if="ai" class="block">
      <h3>{{ t('integrations.ai') }}</h3>
      <div class="form">
        <label class="field"><span>{{ t('integrations.provider') }}</span><input v-model="ai.label" /></label>
        <label class="field"><span>{{ t('integrations.baseUrl') }}</span><input v-model="ai.base_url" class="mono" /></label>
        <label class="field"><span>{{ t('integrations.model') }}</span><input v-model="ai.model" class="mono" /></label>
        <label class="field"><span>{{ t('integrations.apiKey') }} <span class="muted">{{ ai.key_hint || t('integrations.noKey') }}</span></span>
          <input v-model="aiKey" type="password" autocomplete="new-password" :placeholder="t('integrations.keyPlaceholder')" /></label>
        <label class="field"><span>{{ t('integrations.cap') }}</span><input v-model.number="ai.daily_call_cap" type="number" min="0" /></label>
        <div class="field checks">
          <label class="chk"><input type="checkbox" v-model="ai.enabled" /> {{ t('integrations.aiOn') }}</label>
          <label class="chk"><input type="checkbox" v-model="ai.chat_thinking" /> {{ t('integrations.thinking') }}</label>
        </div>
      </div>
      <p class="muted small">{{ t('integrations.anonymise') }}: {{ Object.entries(ai.anonymise || {}).filter(([, v]) => v).map(([k]) => k).join(', ') || '–' }} · {{ t('integrations.anonymisePending') }}</p>
      <div class="row"><button class="btn btn-primary" @click="saveAi">{{ t('common.save') }}</button>
        <button class="btn" @click="testAi">{{ t('integrations.test') }}</button><span class="mono small">{{ aiTest }}</span></div>
    </div>

    <!-- Optimiser: built-in or NVIDIA cuOpt -->
    <div v-if="opt" class="block">
      <h3>{{ t('optimiser.title') }}</h3>
      <p class="muted small">{{ t('optimiser.help') }}</p>
      <div class="form">
        <label class="field"><span>{{ t('optimiser.planEngine') }}</span>
          <select v-model="opt.plan_engine"><option value="builtin">{{ t('optimiser.builtin') }}</option><option value="cuopt">{{ t('optimiser.cuopt') }}</option></select></label>
        <label class="field"><span>{{ t('optimiser.pickEngine') }}</span>
          <select v-model="opt.pick_engine"><option value="builtin">{{ t('optimiser.builtin') }}</option><option value="cuopt">{{ t('optimiser.cuopt') }}</option></select></label>
        <label class="field"><span>{{ t('optimiser.url') }}</span><input v-model="opt.cuopt_url" class="mono" :placeholder="t('optimiser.urlHint')" /></label>
        <label class="field"><span>{{ t('optimiser.token') }} <span class="muted">{{ opt.has_token ? t('optimiser.tokenSet') : t('optimiser.noToken') }}</span></span>
          <input v-model="optToken" type="password" autocomplete="new-password" /></label>
      </div>
      <div class="row"><button class="btn btn-primary" @click="saveOpt()">{{ t('common.save') }}</button>
        <button class="btn" @click="testOpt">{{ t('integrations.test') }}</button>
        <button v-if="opt.has_token" class="btn" @click="saveOpt(true)">{{ t('optimiser.clearToken') }}</button>
        <span class="mono small">{{ optTest }}</span></div>
    </div>

    <!-- ERP connections -->
    <div class="block">
      <div class="row"><h3 class="grow">{{ t('integrations.erp') }}</h3>
        <RouterLink to="erp-inbox" class="btn">{{ t('nav.erpInbox') }}</RouterLink>
        <button class="btn" @click="editErp(null)">{{ t('integrations.addErp') }}</button></div>
      <p class="muted small">{{ t('integrations.erpHelp') }}</p>
      <div v-if="erpForm" class="form edit">
        <label class="field"><span>{{ t('integrations.name') }}</span><input v-model="erpForm.name" required /></label>
        <label class="field"><span>{{ t('integrations.system') }}</span><select v-model="erpForm.system"><option v-for="s in erp.systems" :key="s[0]" :value="s[0]">{{ s[1] }}</option></select></label>
        <label class="field"><span>{{ t('integrations.baseUrl') }}</span><input v-model="erpForm.base_url" class="mono" placeholder="https://" /></label>
        <label class="field"><span>{{ t('integrations.auth') }}</span><select v-model="erpForm.auth_type"><option value="basic">Username + password</option><option value="oauth2">OAuth2 client</option><option value="api_key">API key</option></select></label>
        <label class="field"><span>{{ t('integrations.user') }}</span><input v-model="erpForm.username" autocomplete="off" /></label>
        <label class="field"><span>{{ t('integrations.secret') }} <span class="muted">{{ erpForm.secret_hint }}</span></span><input v-model="erpForm.secret" type="password" autocomplete="new-password" /></label>
        <label class="field"><span>{{ t('integrations.companyCode') }}</span><input v-model="erpForm.company_code" /></label>
        <label class="chk field"><input type="checkbox" v-model="erpForm.enabled" /> {{ t('integrations.enabled') }}</label>
        <div class="row full"><button class="btn btn-primary" @click="saveErp">{{ t('common.save') }}</button><button class="btn" @click="erpForm = null">{{ t('common.cancel') }}</button></div>
      </div>
      <table v-if="erp.connections.length" class="table">
        <thead><tr><th>{{ t('integrations.name') }}</th><th>{{ t('integrations.system') }}</th><th>{{ t('integrations.baseUrl') }}</th><th>{{ t('integrations.secret') }}</th><th>{{ t('integrations.lastTest') }}</th><th></th></tr></thead>
        <tbody><tr v-for="c in erp.connections" :key="c.id"><td>{{ c.name }} <span v-if="c.enabled" class="pill pill-ok">on</span></td><td>{{ c.system }}</td><td class="mono">{{ c.base_url }}</td><td class="mono">{{ c.secret_hint || '–' }}</td>
          <td class="small">{{ c.last_test_result }}<div class="muted">{{ c.last_test_at ? fmtDateTime(c.last_test_at) : '' }}</div></td>
          <td class="row"><button class="btn" @click="editErp(c)">{{ t('common.edit') }}</button><button class="btn" @click="testErp(c)">{{ t('integrations.test') }}</button><button class="btn btn-quiet" @click="removeErp(c)">✕</button></td></tr></tbody>
      </table>
    </div>

    <!-- Read-only API keys -->
    <div class="block">
      <h3>{{ t('integrations.keys') }}</h3>
      <p class="muted small">{{ t('integrations.keysHelp') }}</p>
      <form class="row" @submit.prevent="createKey">
        <label class="field grow"><span>{{ t('integrations.keyName') }}</span><input v-model="keyName" :placeholder="t('integrations.keyNameHint')" required /></label>
        <button class="btn btn-primary">{{ t('integrations.createKey') }}</button>
      </form>
      <div v-if="newKey" class="notice notice-ok"><p>{{ t('integrations.keyOnce') }}</p><p class="mono key">{{ newKey.api_key }}</p><p class="small">{{ newKey.usage }}</p></div>
      <table v-if="keys.length" class="table">
        <thead><tr><th>{{ t('integrations.keyName') }}</th><th>Key</th><th>{{ t('integrations.used') }}</th><th>{{ t('common.status') }}</th><th></th></tr></thead>
        <tbody><tr v-for="k in keys" :key="k.id"><td>{{ k.name }}<div class="muted small">{{ k.created_by }} · {{ fmtDateTime(k.created_at) }}</div></td><td class="mono">{{ k.hint }}</td>
          <td>{{ k.use_count }}<div class="muted small">{{ k.last_used ? fmtDateTime(k.last_used) : '–' }}</div></td>
          <td><span :class="['pill', k.is_active ? 'pill-ok' : 'pill-alarm']">{{ k.is_active ? t('accounts.active') : t('devices.revoke') }}</span></td>
          <td><button v-if="k.is_active" class="btn" @click="revoke(k)">{{ t('devices.revoke') }}</button></td></tr></tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.integ h2 { font-size: var(--text-xl); }
.block { border-top: 1px solid var(--line); padding-top: 16px; display: grid; gap: 10px; }
.block h3 { font-size: var(--text-lg); }
.form { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 14px; }
.edit { background: var(--surface-2); padding: 14px; border-radius: var(--radius); }
.full { grid-column: 1 / -1; }
.checks { align-content: end; }
.chk { display: flex; gap: 6px; align-items: center; }
.chk input { width: auto; min-height: auto; }
.grow { flex: 1; }
.small { font-size: 0.8125rem; }
.key { font-size: 1rem; word-break: break-all; user-select: all; }
</style>
