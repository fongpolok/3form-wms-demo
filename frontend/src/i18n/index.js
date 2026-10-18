import { createI18n } from 'vue-i18n'
import { storage } from '../composables/storage.js'
import en from './en.js'
import zhHant from './zh-hant.js'

export const LANGS = [{ code: 'en', label: 'English' }, { code: 'zh-hant', label: '繁體中文' }]

export const i18n = createI18n({
  legacy: false,
  locale: storage.local.get('lang') || 'en',
  fallbackLocale: 'en',
  messages: { en, 'zh-hant': zhHant },
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
