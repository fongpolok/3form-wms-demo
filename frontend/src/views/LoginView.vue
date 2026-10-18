<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { LANGS, setLang } from '../i18n/index.js'
import { useSession } from '../composables/session.js'
import ThemeSwitch from '../components/ThemeSwitch.vue'

const { t, locale } = useI18n()
const router = useRouter()
const session = useSession()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

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
</style>
