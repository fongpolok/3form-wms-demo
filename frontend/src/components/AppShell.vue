<script setup>
// Layout for PIC and Engineering Manager: one-level sidebar + top bar.
// Navigation items are filtered by role; the brand lives only in the logo tile.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { LANGS, setLang } from '../i18n/index.js'
import { useSession } from '../composables/session.js'
import { useHealth } from '../composables/health.js'
import Icon from './Icon.vue'
import ThemeSwitch from './ThemeSwitch.vue'
import { get } from '../api/client.js'
import { usePolled } from '../composables/poll.js'

const { t, locale } = useI18n()
const session = useSession()
const health = useHealth()
const route = useRoute()
const router = useRouter()

const base = computed(() => (session.role.value === 'PIC' ? '/pic' : '/manager'))
const NAV = [
  { group: 'nav.gProduction' },
  { to: 'progress', icon: 'chart', label: 'nav.progress', min: 'EM' },
  { to: 'plan', icon: 'list', label: 'nav.plan', min: 'EM' },
  { to: 'lean', icon: 'gauge', label: 'nav.lean', min: 'EM' },
  { to: 'advisor', icon: 'people', label: 'nav.advisor', min: 'EM' },
  { to: 'workstations', icon: 'station', label: 'nav.workstations', min: 'EM' },
  { to: 'work-orders', icon: 'list', label: 'nav.workOrders', min: 'EM' },
  { to: 'calendar', icon: 'chart', label: 'nav.calendar', min: 'EM' },
  { to: 'products', icon: 'ruler', label: 'nav.products', min: 'EM' },
  { to: 'scrap', icon: 'flag', label: 'nav.scrap', min: 'EM' },
  { group: 'nav.gWarehouse' },
  { to: 'stock', icon: 'box', label: 'nav.stock', min: 'EM' },
  { to: 'inbound', icon: 'download', label: 'nav.inbound', min: 'EM' },
  { to: 'outbound', icon: 'out', label: 'nav.outbound', min: 'EM' },
  { to: 'bins', icon: 'list', label: 'nav.bins', min: 'EM' },
  { to: 'count', icon: 'check', label: 'nav.count', min: 'EM' },
  { group: 'nav.gAdmin' },
  { to: 'alerts', icon: 'alert', label: 'nav.alerts', min: 'EM' },
  { to: 'export', icon: 'download', label: 'nav.export', min: 'EM' },
  { to: 'sop', icon: 'list', label: 'nav.sop', min: 'EM' },
  { to: 'accounts', icon: 'people', label: 'nav.accounts', min: 'PIC' },
  { to: 'devices', icon: 'tablet', label: 'nav.devices', min: 'PIC' },
  { to: 'audit', icon: 'shield', label: 'nav.audit', min: 'PIC' },
  { to: 'settings', icon: 'gear', label: 'nav.settings', min: 'EM' },
]
const alerts = usePolled(() => get('/api/v1/alerts'), 20000)
const alarmCount = computed(() => (alerts.data.value || []).length)
const q = ref('')
function search() { if (q.value.trim()) router.push({ path: `${base.value}/search`, query: { q: q.value.trim() } }) }
const items = computed(() => NAV.filter((n) => n.group || session.can(n.min)))

async function logout() {
  await session.logout()
  router.push('/login')
}
</script>

<template>
  <div class="shell">
    <a class="skip" href="#main">Skip to content</a>
    <aside class="side" :aria-label="t('app.name')">
      <div class="brand">
        <img src="/brand/logo.png" alt="" width="36" height="36" />
        <div>
          <strong>{{ t('app.name') }}</strong>
          <span class="muted">{{ t('app.tagline') }}</span>
        </div>
      </div>
      <nav>
        <template v-for="n in items" :key="n.to || n.group">
          <p v-if="n.group" class="group">{{ t(n.group) }}</p>
          <RouterLink v-else :to="`${base}/${n.to}`" class="nav-item"
                      :aria-current="route.path.endsWith('/' + n.to) ? 'page' : undefined">
            <Icon :name="n.icon" :size="20" /> <span>{{ t(n.label) }}</span>
          </RouterLink>
        </template>
      </nav>
    </aside>

    <div class="main-col">
      <header class="top">
        <span v-if="!health.serverOk" class="pill pill-alarm"><Icon name="wifi" :size="16" /> {{ t('common.offline') }}</span>
        <form class="topsearch" role="search" @submit.prevent="search">
          <input v-model="q" type="search" :placeholder="t('search.placeholder')" :aria-label="t('common.search')" />
        </form>
        <span class="spacer"></span>
        <RouterLink :to="`${base}/alerts`" class="bell" :aria-label="`${t('nav.alerts')}: ${alarmCount}`">
          <Icon name="alert" :size="20" /><span v-if="alarmCount" class="count">{{ alarmCount }}</span>
        </RouterLink>
        <ThemeSwitch />
        <label class="lang">
          <span class="sr-only">{{ t('common.language') }}</span>
          <select :value="locale" @change="setLang($event.target.value)">
            <option v-for="l in LANGS" :key="l.code" :value="l.code">{{ l.label }}</option>
          </select>
        </label>
        <div class="who">
          <strong>{{ session.state.account?.display_name }}</strong>
          <span class="muted">{{ t(`role.${session.role.value}`) }}</span>
        </div>
        <button class="btn" @click="logout"><Icon name="out" :size="18" /> {{ t('common.logout') }}</button>
      </header>
      <main id="main" tabindex="-1"><RouterView /></main>
    </div>
  </div>
</template>

<style scoped>
.shell { display: grid; grid-template-columns: 248px 1fr; min-height: 100vh; }
.skip { position: absolute; left: -999px; }
.skip:focus { left: 12px; top: 12px; z-index: 10; background: var(--surface); padding: 8px 12px; }
.side { background: var(--surface); border-right: 1px solid var(--line); padding: 20px 12px; position: sticky; top: 0; height: 100vh; overflow-y: auto; }
.brand { display: flex; gap: 12px; align-items: center; padding: 0 8px 20px; }
.brand img { border-radius: 8px; }
.brand div { display: grid; line-height: 1.25; }
.brand span { font-size: 0.8125rem; }
nav { display: grid; gap: 2px; }
.nav-item { display: flex; align-items: center; gap: 12px; min-height: 44px; padding: 0 12px; border-radius: var(--radius);
            color: var(--ink); text-decoration: none; font-weight: 500; }
.nav-item:hover { background: var(--surface-2); }
.group { margin: 14px 12px 4px; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-2); }
.topsearch input { min-height: 40px; width: min(280px, 30vw); }
.who strong { white-space: nowrap; }
.bell { position: relative; display: grid; place-items: center; width: 44px; height: 44px; border-radius: var(--radius); color: var(--ink); }
.bell:hover { background: var(--surface-2); }
.count { position: absolute; top: 4px; right: 2px; min-width: 20px; height: 20px; padding: 0 5px; border-radius: 10px;
         background: #b91c1c; color: #fff; font-size: 0.75rem; font-weight: 700; display: grid; place-items: center; }
.nav-item[aria-current='page'] { background: var(--accent-soft); color: var(--accent); font-weight: 650; }
.main-col { min-width: 0; display: grid; grid-template-rows: auto 1fr; }
.top { display: flex; align-items: center; gap: 16px; padding: 12px 28px; border-bottom: 1px solid var(--line); background: var(--surface); }
.who { display: grid; text-align: right; line-height: 1.25; }
.who span { font-size: 0.8125rem; }
.lang select { min-height: 40px; width: auto; }
main { padding: 28px; max-width: 1280px; width: 100%; outline: none; }
@media (max-width: 900px) {
  .shell { grid-template-columns: 1fr; }
  .side { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  nav { grid-auto-flow: column; overflow-x: auto; }
  .group { display: none; }
  .nav-item span { white-space: nowrap; }
  .top { padding: 12px 16px; flex-wrap: wrap; }
  main { padding: 16px; }
}
</style>
