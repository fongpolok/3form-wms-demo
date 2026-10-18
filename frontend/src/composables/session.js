import { computed, reactive } from 'vue'
import { get, onUnauthorized, post } from '../api/client.js'
import { storage } from './storage.js'

const RANK = { WORKER: 1, EM: 2, PIC: 3 }
const state = reactive({ account: storage.session.getJSON('account', null), device: null })

function save(payload) {
  storage.session.set('token', payload.token)
  storage.session.setJSON('account', payload.account)
  if (payload.account?.legacy_staff_pk) storage.session.set('operator', String(payload.account.legacy_staff_pk))
  state.account = payload.account
  state.device = payload.device || null
}

function clear() {
  ;['token', 'account', 'operator'].forEach((k) => storage.session.remove(k))
  state.account = null
}

onUnauthorized(clear)

export function useSession() {
  return {
    state,
    isLoggedIn: computed(() => !!state.account),
    role: computed(() => state.account?.role),
    can: (minRole) => (RANK[state.account?.role] || 0) >= RANK[minRole],
    homePath: computed(() => ({ PIC: '/pic', EM: '/manager', WORKER: '/worker' })[state.account?.role] || '/login'),
    async login(username, password) { save(await post('/api/v1/auth/login', { username, password })) },
    async workerLogin(staffId) { save(await post('/api/v1/auth/worker-login', { staff_id: staffId })) },
    async refresh() { const me = await get('/api/v1/auth/me'); state.account = me.account; state.device = me.device },
    async logout() { try { await post('/api/v1/auth/logout') } finally { clear() } },
  }
}
