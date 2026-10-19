import { createI18n } from 'vue-i18n'
import { storage } from '../composables/storage.js'
import en from './en.js'
import zhHant from './zh-hant.js'
import phase2 from './phase2.js'
import phase3 from './phase3.js'
import phase4 from './phase4.js'

function merge(base, extra) {
  const out = { ...base }
  for (const [k, v] of Object.entries(extra)) out[k] = typeof v === 'object' && !Array.isArray(v) ? merge(base[k] || {}, v) : v
  return out
}

export const LANGS = [{ code: 'en', label: 'English' }, { code: 'zh-hant', label: '繁體中文' }]

export const i18n = createI18n({
  legacy: false,
  locale: storage.local.get('lang') || 'en',
  fallbackLocale: 'en',
  messages: { en: [phase2.en, phase3.en, phase4.en].reduce(merge, en),
              'zh-hant': [phase2['zh-hant'], phase3['zh-hant'], phase4['zh-hant']].reduce(merge, zhHant) },
})

export function setLang(code) {
  i18n.global.locale.value = code
  storage.local.set('lang', code)
  document.documentElement.lang = code === 'zh-hant' ? 'zh-Hant' : 'en'
}

// Industry YAML stores names as { en, 'zh-hant' }; pick the current language.
export function pick(obj) {
  if (obj == null || typeof obj === 'string') return obj ?? ''
  return obj[i18n.global.locale.value] || obj.en || ''
}

// Dates and times in the app's language (not the browser's).
export function appLocale() {
  return i18n.global.locale.value === 'zh-hant' ? 'zh-Hant-HK' : 'en-GB'
}

export function fmtDateTime(value) {
  if (!value) return ''
  const loc = i18n.global.locale.value === 'zh-hant' ? 'zh-Hant-HK' : 'en-GB'
  return new Date(value).toLocaleString(loc, { dateStyle: 'medium', timeStyle: 'short' })
}
