// Thin wrapper around fetch: adds the login token, turns errors into plain
// messages, and tells the session layer when the server says "log in again".
import { storage } from '../composables/storage.js'

const listeners = new Set()
export function onUnauthorized(fn) { listeners.add(fn); return () => listeners.delete(fn) }

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

function headers(extra = {}) {
  const h = { 'Content-Type': 'application/json', ...extra }
  const token = storage.session.get('token')
  if (token) h.Authorization = `Bearer ${token}`
  const deviceToken = storage.local.get('deviceToken')
  if (deviceToken) h['X-Device-Token'] = deviceToken
  const operator = storage.session.get('operator')
  if (operator) h.operator = operator // legacy WMS endpoints expect this
  return h
}

// Slow work (planning with cuOpt, comparisons) passes a longer timeoutMs; see SLOW_MS.
export const SLOW_MS = 180000
export async function api(path, { method = 'GET', body, raw = false, timeoutMs = 8000 } = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  let res
  try {
    res = await fetch(path, { method, headers: headers(), body: body ? JSON.stringify(body) : undefined, signal: ctrl.signal })
  } catch (e) {
    throw new ApiError('Cannot reach the server. Check the network cable or Wi-Fi.', 0)
  } finally {
    clearTimeout(timer)
  }
  if (raw && res.ok) return res
  let data = null
  const type = res.headers.get('content-type') || ''
  if (type.includes('json')) data = await res.json()
  if (!res.ok || (data && data.status_code >= 400)) {
    const status = data?.status_code || res.status
    if (status === 401) listeners.forEach((fn) => fn())
    throw new ApiError(data?.detail || `Request failed (${status}).`, status)
  }
  return data
}

export const get = (p, opts = {}) => api(p, opts)
export const post = (p, body, opts = {}) => api(p, { method: 'POST', body, ...opts })
export const patch = (p, body) => api(p, { method: 'PATCH', body })
export const put = (p, body) => api(p, { method: 'PUT', body })
export const del = (p) => api(p, { method: 'DELETE' })

export async function download(path, filename) {
  const res = await api(path, { raw: true, timeoutMs: 60000 })
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function newEventId() {
  return (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`).replace(/-/g, '')
}
