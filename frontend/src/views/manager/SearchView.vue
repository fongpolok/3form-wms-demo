<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { get } from '../../api/client.js'
import { fmtDateTime } from '../../i18n/index.js'
import PageHead from '../../components/PageHead.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const q = ref(route.query.q || '')
const kind = ref('')
const results = ref(null)
const error = ref('')
const KINDS = ['', 'sop', 'scrap_note', 'stop_note', 'work_order', 'advice']

async function run() {
  if (!q.value.trim()) { results.value = null; return }
  error.value = ''
  try { results.value = await get(`/api/v1/search?q=${encodeURIComponent(q.value)}${kind.value ? `&kinds=${kind.value}` : ''}`) }
  catch (e) { error.value = e.message }
}
watch(() => route.query.q, (v) => { q.value = v || ''; run() }, { immediate: true })
watch(kind, run)
function submit() { router.replace({ query: { q: q.value } }) }
</script>

<template>
  <PageHead :title="t('search.title')" :subtitle="t('search.subtitle')" />
  <form class="card row" role="search" @submit.prevent="submit">
    <label class="field grow"><span>{{ t('common.search') }}</span><input v-model="q" type="search" :placeholder="t('search.placeholder')" /></label>
    <label class="field"><span>{{ t('search.kind') }}</span><select v-model="kind"><option v-for="k in KINDS" :key="k" :value="k">{{ t(`search.kinds.${k || 'all'}`) }}</option></select></label>
    <button class="btn btn-primary">{{ t('common.search') }}</button>
  </form>
  <p v-if="error" class="notice notice-error">{{ error }}</p>
  <p v-if="results && !results.length" class="muted block">{{ t('search.none') }}</p>
  <div class="stack block">
    <article v-for="r in results || []" :key="r.doc_id" class="card hit">
      <div class="row"><span class="pill pill-info">{{ t(`search.kinds.${r.kind}`) }}</span><strong>{{ r.title }}</strong>
        <span class="muted small">{{ r.ref }} · {{ fmtDateTime(r.ts) }}</span></div>
      <p>{{ r.snippet }}</p>
    </article>
  </div>
</template>

<style scoped>
.grow { flex: 1; min-width: 240px; }
.row { align-items: flex-end; }
.block { margin-top: 16px; }
.hit .row { align-items: center; }
.small { font-size: 0.8125rem; }
</style>
