<script setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { LANGS, pick, setLang } from '../i18n/index.js'
import { get } from '../api/client.js'
import { useSession } from '../composables/session.js'
import ThemeSwitch from '../components/ThemeSwitch.vue'

const { t, locale } = useI18n()
const router = useRouter()
const session = useSession()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)
const demo = ref(null)            // public website demo info, or null
const demoWs = ref('WS-01')

onMounted(async () => {
  try {
    const info = await get('/api/v1/auth/public-demo')
    if (info.enabled) { demo.value = info; demoWs.value = info.workstations[0]?.code || 'WS-01' }
  } catch { /* normal sign-in still works */ }
})

async function tryAs(role) {
  error.value = ''
  busy.value = true
  try {
    await session.demoLogin(role, role === 'worker' ? demoWs.value : '')
    router.push(role === 'worker' ? '/worker' : session.homePath.value)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await session.login(username.value.trim(), password.value)
    router.push(session.homePath.value)
  } catch (e) {
    error.value = e.message
    password.value = ''
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="page">
    <form class="card panel stack" @submit.prevent="submit" aria-labelledby="login-title">
      <div class="brand">
        <img src="/brand/logo.png" alt="3Form" width="56" height="56" />
        <div>
          <h1 id="login-title">{{ t('login.title') }}</h1>
          <p class="muted">{{ t('login.subtitle') }}</p>
        </div>
      </div>
      <section v-if="demo" class="stack" aria-labelledby="demo-title">
        <h2 id="demo-title">{{ t('demo.title') }}</h2>
        <p class="muted">{{ t('demo.intro') }}</p>
        <button type="button" class="btn btn-primary try" :disabled="busy" @click="tryAs('pic')">
          <strong>{{ t('demo.pic') }}</strong><span>{{ t('demo.picHint') }}</span>
        </button>
        <button type="button" class="btn try" :disabled="busy" @click="tryAs('em')">
          <strong>{{ t('demo.em') }}</strong><span>{{ t('demo.emHint') }}</span>
        </button>
        <div class="row worker-try">
          <button type="button" class="btn try grow" :disabled="busy" @click="tryAs('worker')">
            <strong>{{ t('demo.worker') }}</strong><span>{{ t('demo.workerHint') }}</span>
          </button>
          <label>
            <span class="sr-only">{{ t('demo.workstation') }}</span>
            <select v-model="demoWs" class="ws">
              <option v-for="w in demo.workstations" :key="w.code" :value="w.code">{{ w.code }} · {{ pick(w.step_name) }}</option>
            </select>
          </label>
        </div>
        <p class="notice small">{{ t('demo.notes', { n: demo.ai_daily_calls }) }}</p>
      </section>
      <template v-else>
      <label class="field">
        <span>{{ t('login.username') }}</span>
        <input v-model="username" autocomplete="username" autocapitalize="off" spellcheck="false" required />
      </label>
      <label class="field">
        <span>{{ t('login.password') }}</span>
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <button class="btn btn-primary" type="submit" :disabled="busy">{{ busy ? t('common.loading') : t('login.submit') }}</button>
      </template>
      <p v-if="demo && error" class="notice notice-error" role="alert">{{ error }}</p>
      <div class="row foot">
        <RouterLink to="/worker">{{ t('login.workerLink') }}</RouterLink>
        <span class="spacer"></span>
        <ThemeSwitch />
        <label>
          <span class="sr-only">{{ t('common.language') }}</span>
          <select :value="locale" @change="setLang($event.target.value)" class="lang">
            <option v-for="l in LANGS" :key="l.code" :value="l.code">{{ l.label }}</option>
          </select>
        </label>
      </div>
    </form>
  </div>
</template>

<style scoped>
.page { min-height: 100vh; display: grid; place-items: center; padding: 16px; }
.panel { width: min(420px, 100%); padding: 32px; }
.brand { display: flex; gap: 16px; align-items: center; margin-bottom: 8px; }
.brand img { border-radius: 12px; }
.foot { font-size: var(--text-sm); }
.lang { width: auto; min-height: 40px; }
.try { display: grid; justify-items: start; gap: 2px; text-align: left; padding: 12px 16px; height: auto; }
.try span { font-size: var(--text-sm); font-weight: 400; opacity: .85; }
.worker-try { flex-wrap: nowrap; align-items: stretch; }
.worker-try .grow { flex: 1; }
.ws { width: auto; height: 100%; }
.small { font-size: var(--text-sm); color: var(--ink-2); border-color: var(--line); }
@media (max-width: 420px) { .worker-try { flex-wrap: wrap; } .ws { width: 100%; } }
</style>
