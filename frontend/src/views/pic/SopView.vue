<script setup>
// RAG / company SOP library: uploaded SOPs become searchable passages the agent can quote.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { del, get } from '../../api/client.js'
import { storage } from '../../composables/storage.js'
import { fmtDateTime } from '../../i18n/index.js'
import { useSession } from '../../composables/session.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'

const { t } = useI18n()
const session = useSession()
const docs = usePolled(() => get('/api/v1/sop'), 0)
const file = ref(null)
const title = ref('')
const msg = ref({ text: '', kind: 'ok' })
const busy = ref(false)

async function upload() {
  if (!file.value) return
  busy.value = true
  const fd = new FormData()
  fd.append('file', file.value)
  fd.append('title', title.value)
  try {
    const res = await fetch('/api/v1/sop', { method: 'POST', body: fd, headers: { Authorization: `Bearer ${storage.session.get('token')}` } })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Upload failed')
    msg.value = { kind: 'ok', text: t('sop.done', { title: data.title, n: data.chunks }) }
    title.value = ''; file.value = null; docs.reload()
  } catch (e) { msg.value = { kind: 'error', text: e.message } } finally { busy.value = false }
}
async function remove(d) {
  if (!confirm(t('sop.confirmRemove', { title: d.title }))) return
  try { await del(`/api/v1/sop/${d.sop_id}`); docs.reload() } catch (e) { msg.value = { kind: 'error', text: e.message } }
}
</script>

<template>
  <PageHead :title="t('nav.sop')" :subtitle="t('sop.subtitle')" />
  <form v-if="session.can('PIC')" class="card row up" @submit.prevent="upload">
    <label class="field grow"><span>{{ t('sop.file') }}</span><input type="file" accept=".pdf,.docx,.md,.txt" @change="file = $event.target.files[0]" required /></label>
    <label class="field grow"><span>{{ t('sop.title') }}</span><input v-model="title" :placeholder="t('sop.titleHint')" /></label>
    <button class="btn btn-primary" :disabled="busy || !file">{{ busy ? t('common.loading') : t('sop.upload') }}</button>
  </form>
  <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>
  <section class="card block">
    <h2>{{ t('sop.library') }}</h2>
    <p v-if="docs.data.value && !docs.data.value.length" class="muted">{{ t('sop.empty') }}</p>
    <div v-else class="table-wrap"><table class="table">
      <thead><tr><th>{{ t('sop.title') }}</th><th>{{ t('sop.file') }}</th><th>{{ t('sop.passages') }}</th><th>{{ t('sop.by') }}</th><th></th></tr></thead>
      <tbody><tr v-for="d in docs.data.value || []" :key="d.sop_id">
        <td><strong>{{ d.title }}</strong><div class="muted mono">{{ d.sop_id }}</div></td><td>{{ d.filename }}<div class="muted">{{ (d.size / 1024).toFixed(0) }} KB<template v-if="d.pages"> · {{ d.pages }} p</template></div></td>
        <td>{{ d.chunks }}</td><td>{{ d.uploaded_by }}<div class="muted">{{ fmtDateTime(d.uploaded_at) }}</div></td>
        <td><button v-if="session.can('PIC')" class="btn" @click="remove(d)">{{ t('products.remove') }}</button></td></tr></tbody>
    </table></div>
  </section>
  <section class="card block muted">
    <h2>{{ t('sop.ragTitle') }}</h2>
    <p>{{ t('sop.ragText') }}</p>
  </section>
</template>

<style scoped>
.up { align-items: flex-end; }
.grow { flex: 1; min-width: 220px; }
.block { margin-top: 16px; }
.block h2 { font-size: var(--text-lg); margin-bottom: 10px; color: var(--ink); }
</style>
