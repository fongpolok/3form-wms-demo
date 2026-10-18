// Colour theme per device: 'light' (default), 'dark', or 'auto' (follow the system).
import { ref } from 'vue'
import { storage } from './storage.js'

export const THEMES = ['light', 'dark', 'auto']
export const theme = ref(storage.local.get('theme') || 'light')

export function applyTheme(value = theme.value) {
  theme.value = THEMES.includes(value) ? value : 'light'
  document.documentElement.dataset.theme = theme.value
  storage.local.set('theme', theme.value)
}
