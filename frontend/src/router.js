import { createRouter, createWebHistory } from 'vue-router'
import { useSession } from './composables/session.js'
import AppShell from './components/AppShell.vue'

const RANK = { WORKER: 1, EM: 2, PIC: 3 }

// Same pages for EM (/manager) and PIC (/pic); PIC-only pages carry min: 'PIC'.
const pages = [
  { path: 'progress', component: () => import('./views/manager/ProgressView.vue'), min: 'EM' },
  { path: 'lean', component: () => import('./views/manager/LeanView.vue'), min: 'EM' },
  { path: 'plan', component: () => import('./views/manager/PlanView.vue'), min: 'EM' },
  { path: 'advisor', component: () => import('./views/manager/AdvisorView.vue'), min: 'EM' },
  { path: 'search', component: () => import('./views/manager/SearchView.vue'), min: 'EM' },
  { path: 'sop', component: () => import('./views/pic/SopView.vue'), min: 'EM' },
  { path: 'calendar', component: () => import('./views/pic/CalendarView.vue'), min: 'EM' },
  { path: 'workstations', component: () => import('./views/manager/WorkstationsView.vue'), min: 'EM' },
  { path: 'products', component: () => import('./views/manager/ProductsView.vue'), min: 'EM' },
  { path: 'alerts', component: () => import('./views/manager/AlertsView.vue'), min: 'EM' },
  { path: 'inbound', component: () => import('./views/warehouse/InboundView.vue'), min: 'EM' },
  { path: 'outbound', component: () => import('./views/warehouse/OutboundView.vue'), min: 'EM' },
  { path: 'bins', component: () => import('./views/warehouse/BinsView.vue'), min: 'EM' },
  { path: 'count', component: () => import('./views/warehouse/CountView.vue'), min: 'EM' },
  { path: 'work-orders', component: () => import('./views/manager/WorkOrdersView.vue'), min: 'EM' },
  { path: 'scrap', component: () => import('./views/manager/ScrapView.vue'), min: 'EM' },
  { path: 'stock', component: () => import('./views/manager/StockView.vue'), min: 'EM' },
  { path: 'export', component: () => import('./views/manager/ExportView.vue'), min: 'EM' },
  { path: 'settings', component: () => import('./views/pic/SettingsView.vue'), min: 'EM' },
  { path: 'accounts', component: () => import('./views/pic/AccountsView.vue'), min: 'PIC' },
  { path: 'devices', component: () => import('./views/pic/DevicesView.vue'), min: 'PIC' },
  { path: 'audit', component: () => import('./views/pic/AuditView.vue'), min: 'PIC' },
]
const area = (prefix, min) => ({
  path: prefix, component: AppShell, meta: { min },
  children: [{ path: '', redirect: `${prefix}/progress` },
    ...pages.map((p) => ({ path: p.path, component: p.component, meta: { min: p.min } }))],
})

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', component: () => import('./views/LoginView.vue') },
    { path: '/worker', component: () => import('./views/worker/WorkerStation.vue') },
    area('/manager', 'EM'),
    area('/pic', 'PIC'),
    { path: '/:rest(.*)*', redirect: '/login' },
  ],
})

router.beforeEach((to) => {
  const session = useSession()
  const min = to.matched.reduce((m, r) => (RANK[r.meta.min] > RANK[m] ? r.meta.min : m), 'WORKER')
  if (to.path === '/login' && session.isLoggedIn.value && session.role.value !== 'WORKER') return session.homePath.value
  if (!to.matched.some((r) => r.meta.min)) return true
  if (!session.isLoggedIn.value || session.role.value === 'WORKER') return '/login'
  if (RANK[session.role.value] < RANK[min]) return session.homePath.value
  // A PIC who opens /manager/... lands in the PIC area with the same page.
  if (session.role.value === 'PIC' && to.path.startsWith('/manager')) return to.path.replace('/manager', '/pic')
  return true
})
