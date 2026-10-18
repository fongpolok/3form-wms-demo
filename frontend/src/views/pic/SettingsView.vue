<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, post } from '../../api/client.js'
import { useSession } from '../../composables/session.js'
import { pick } from '../../i18n/index.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'

const { t } = useI18n()
const { data, error, reload } = usePolled(() => get('/api/v1/mes/settings'), 0)
const session = useSession()
const ind = usePolled(() => get('/api/v1/settings/industry'), 0)
const msg = ref('')
async function setIndustry(code) {
  try {
    await post('/api/v1/settings/industry', { code })
    msg.value = t('settings.industryChanged')
    ind.reload(); setTimeout(reload, 300)
  } catch (e) { msg.value = e.message }
}
</script>

<template>
  <PageHead :title="t('settings.title')" :subtitle="t('settings.subtitle')" />
  <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
  <section v-if="ind.data.value" class="card row industry">
    <label class="field"><span>{{ t('settings.industry') }}</span>
      <select :value="ind.data.value.current" :disabled="!session.can('PIC')" @change="setIndustry($event.target.value)">
        <option v-for="o in ind.data.value.options" :key="o.code" :value="o.code">{{ pick(o.label) }} · {{ o.stock_rule.toUpperCase() }}</option>
      </select></label>
    <p class="muted grow">{{ session.can('PIC') ? t('settings.industryHelp') : t('settings.industryPicOnly') }}</p>
    <p v-if="msg" class="notice notice-ok" role="status">{{ msg }}</p>
  </section>
  <div v-if="data" class="grid">
    <section class="card stack">
      <h2>{{ t('settings.industry') }}: {{ pick(data.industry.label) }}</h2>
      <h3>{{ t('settings.steps') }}</h3>
      <ol class="list">
        <li v-for="s in data.industry.steps" :key="s.code">
          {{ pick(s.name) }} <span class="muted mono">{{ s.code }} · {{ s.std_seconds_per_unit }}s/pc</span>
          <span v-if="s.measurement" class="pill pill-info">{{ s.measurement.name }} {{ s.measurement.target }}{{ s.measurement.unit }}</span>
        </li>
      </ol>
      <h3>{{ t('settings.scrapReasons') }}</h3>
      <ul class="list"><li v-for="r in data.industry.scrap_reasons" :key="r.code">{{ pick(r) }} <span class="muted mono">{{ r.code }}</span></li></ul>
    </section>
    <section class="card">
      <pre class="mono yaml">{{ JSON.stringify(data.settings, null, 2) }}</pre>
    </section>
  </div>
</template>

<style scoped>
.industry { margin-bottom: 16px; align-items: flex-end; }
.industry .field { width: 300px; }
.grow { flex: 1; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; align-items: start; }
.list { margin: 0; padding-left: 1.3em; display: grid; gap: 6px; }
.yaml { margin: 0; font-size: 0.875rem; white-space: pre-wrap; max-height: 70vh; overflow: auto; }
</style>
