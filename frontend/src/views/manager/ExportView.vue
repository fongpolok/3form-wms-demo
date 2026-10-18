<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { download } from '../../api/client.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'

const { t } = useI18n()
const iso = (d) => d.toISOString().slice(0, 10)
const to = ref(iso(new Date()))
const from = ref(iso(new Date(Date.now() - 30 * 864e5)))
const error = ref('')
const busy = ref(false)

async function go() {
  error.value = ''; busy.value = true
  try { await download(`/api/v1/reports/production.xlsx?from=${from.value}&to=${to.value}`, `3form_production_${from.value}_${to.value}.xlsx`) }
  catch (e) { error.value = e.message }
  finally { busy.value = false }
}
</script>

<template>
  <PageHead :title="t('export.title')" :subtitle="t('export.subtitle')" />
  <form class="card row" @submit.prevent="go">
    <label class="field"><span>{{ t('common.from') }}</span><input type="date" v-model="from" required /></label>
    <label class="field"><span>{{ t('common.to') }}</span><input type="date" v-model="to" required /></label>
    <button class="btn btn-primary" :disabled="busy"><Icon name="download" :size="18" /> {{ busy ? t('common.loading') : t('export.download') }}</button>
  </form>
  <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
</template>

<style scoped>.row { align-items: flex-end; }</style>
