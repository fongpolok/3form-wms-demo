import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router.js'
import { fmtDateTime, i18n, setLang } from './i18n/index.js'
import { applyTheme } from './composables/theme.js'
import './styles/tokens.css'
import './styles/base.css'

setLang(i18n.global.locale.value)
applyTheme()
const app = createApp(App)
app.config.globalProperties.$dt = fmtDateTime
app.use(i18n).use(router).mount('#app')
