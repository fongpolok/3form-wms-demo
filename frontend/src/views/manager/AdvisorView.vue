<script setup>
// AI Advisor: advice cards from the four agent jobs (Accept / Reject only records
// a decision; the agent never changes data), the ask-the-agent chat, and usage.
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, get, post } from '../../api/client.js'
import { fmtDateTime } from '../../i18n/index.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'

const { t, locale } = useI18n()
const status = ref('open')
const job = ref('')
const advice = usePolled(() => get(`/api/v1/agent/advice?status=${status.value}`), 60000)
const chats = usePolled(() => get('/api/v1/agent/chat'), 0)
const busy = ref(false)
const msg = ref({ text: '', kind: 'ok' })
const comments = ref({})
const question = ref('')
const conversation = ref(null)
const thinking = ref(false)
const log = ref(null)

const items = computed(() => (advice.data.value?.items || []).filter((a) => !job.value || a.job === job.value))
const zh = computed(() => locale.value === 'zh-hant')
const pickLang = (a, f) => (zh.value && a[`${f}_zh`]) || a[f]
const sev = { alarm: ['pill-alarm', 'alert'], warn: ['pill-warn', 'alert'], info: ['pill-info', 'check'] }

async function runNow() {
  busy.value = true
  try {
    const r = await api('/api/v1/agent/run', { method: 'POST', timeoutMs: 180000, body: job.value ? { job: job.value } : {} })
    msg.value = { kind: 'ok', text: t('advisor.ran', { n: r.results.reduce((s, x) => s + x.findings, 0) }) }
    advice.reload()
  } catch (e) { msg.value = { kind: 'error', text: e.message } } finally { busy.value = false }
}
async function decide(a, accept) {
  try { await post(`/api/v1/agent/advice/${a.advice_id}/decision`, { accept, comment: comments.value[a.advice_id] || '' }); advice.reload() }
  catch (e) { msg.value = { kind: 'error', text: e.message } }
}
async function ask() {
  const q = question.value.trim()
  if (!q) return
  thinking.value = true
  conversation.value = conversation.value || { conversation_id: null, turns: [] }
  conversation.value.turns.push({ q, a: null })
  question.value = ''
  await nextTick(); log.value?.scrollTo({ top: 1e6 })
  try {
    // The agent may chain several look-ups: allow up to 2 minutes (normal requests time out after 8 s).
    const r = await api('/api/v1/agent/chat', { method: 'POST', timeoutMs: 120000,
      body: { question: q, conversation_id: conversation.value.conversation_id, lang: locale.value } })
    conversation.value.conversation_id = r.conversation_id
    conversation.value.turns[conversation.value.turns.length - 1] = r
  } catch (e) {
    conversation.value.turns[conversation.value.turns.length - 1] = { q, a: e.message, tools: [] }
  } finally {
    thinking.value = false
    await nextTick(); log.value?.scrollTo({ top: 1e6 })
  }
}
function openConversation(c) { conversation.value = JSON.parse(JSON.stringify(c)) }
// Minimal, safe formatting for the AI's answer: escape HTML, then **bold** and line breaks.
function render(text) {
  const esc = String(text || '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
  return esc.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>')
}
</script>

<template>
  <PageHead :title="t('nav.advisor')" :subtitle="t('advisor.subtitle')">
    <button class="btn btn-primary" :disabled="busy" @click="runNow">{{ busy ? t('common.loading') : t('advisor.runNow') }}</button>
  </PageHead>

  <p v-if="advice.data.value && !advice.data.value.ai_available" class="notice offline" role="status">
    <Icon name="wifi" :size="18" /> {{ t('advisor.offline') }}: {{ advice.data.value.offline_reason }} {{ t('advisor.offlineHelp') }}
  </p>
  <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>

  <div class="layout">
    <section class="stack">
      <div class="row filters">
        <div class="seg" role="radiogroup" :aria-label="t('common.status')">
          <button v-for="s in ['open', 'accepted', 'rejected', 'all']" :key="s" type="button" role="radio" :aria-checked="status === s"
                  :class="{ on: status === s }" @click="status = s; advice.reload()">{{ t(`advisor.status.${s}`) }}</button>
        </div>
        <select v-model="job" :aria-label="t('advisor.job')" class="job">
          <option value="">{{ t('advisor.allJobs') }}</option>
          <option v-for="j in ['work_orders', 'progress', 'stock_take', 'inventory']" :key="j" :value="j">{{ t(`advisor.jobs.${j}`) }}</option>
        </select>
        <span class="muted small" v-if="advice.data.value?.last_run">{{ t('advisor.lastRun', { when: fmtDateTime(advice.data.value.last_run.ts) }) }}</span>
      </div>
      <p v-if="advice.data.value && !items.length" class="muted">{{ t('advisor.none') }}</p>
      <article v-for="a in items" :key="a.advice_id" class="card advice">
        <div class="row">
          <span :class="['pill', sev[a.severity]?.[0] || 'pill-info']"><Icon :name="sev[a.severity]?.[1] || 'check'" :size="14" /> {{ t(`advisor.jobs.${a.job}`) }}</span>
          <span class="muted small">{{ a.source === 'ai' ? `AI · ${a.model}` : t('advisor.rules') }} · {{ fmtDateTime(a.updated_at || a.created_at) }}</span>
        </div>
        <h3>{{ pickLang(a, 'title') }}</h3>
        <p>{{ pickLang(a, 'finding') }}</p>
        <p class="suggest"><strong>{{ t('advisor.suggestion') }}:</strong> {{ pickLang(a, 'suggestion') }}</p>
        <details><summary>{{ t('advisor.numbers') }}</summary><pre class="mono facts">{{ JSON.stringify(a.facts, null, 2) }}</pre></details>
        <div v-if="a.status === 'open'" class="row decide">
          <input v-model="comments[a.advice_id]" :placeholder="t('advisor.comment')" :aria-label="t('advisor.comment')" />
          <button class="btn btn-primary" @click="decide(a, true)">{{ t('advisor.accept') }}</button>
          <button class="btn" @click="decide(a, false)">{{ t('advisor.reject') }}</button>
        </div>
        <p v-else class="muted small">{{ t(`advisor.status.${a.status}`) }} · {{ a.decided_by }}<template v-if="a.decision_comment"> · “{{ a.decision_comment }}”</template></p>
      </article>
    </section>

    <aside class="stack">
      <section class="card chat">
        <h2>{{ t('advisor.ask') }}</h2>
        <p class="muted small">{{ t('advisor.askHelp') }}</p>
        <div ref="log" class="log" aria-live="polite">
          <template v-for="(turn, i) in conversation?.turns || []" :key="i">
            <p class="q">{{ turn.q }}</p>
            <div v-if="turn.a != null" class="a"><span v-html="render(turn.a)"></span>
              <p v-if="turn.tools?.length" class="muted small tools">{{ t('advisor.looked') }}: {{ turn.tools.map((x) => x.tool).join(', ') }}</p></div>
            <p v-else class="a muted">{{ t('advisor.thinking') }}</p>
          </template>
          <p v-if="!conversation" class="muted small">{{ t('advisor.examples') }}</p>
        </div>
        <form class="row ask" @submit.prevent="ask">
          <textarea v-model="question" :placeholder="t('advisor.placeholder')" :aria-label="t('advisor.ask')" rows="2" @keydown.enter.exact.prevent="ask"></textarea>
          <button class="btn btn-primary" :disabled="thinking || !question.trim()">{{ t('advisor.send') }}</button>
        </form>
        <button v-if="conversation" type="button" class="btn btn-quiet small" @click="conversation = null">{{ t('advisor.newChat') }}</button>
      </section>
      <section class="card stack" v-if="chats.data.value?.length">
        <h2>{{ t('advisor.history') }}</h2>
        <button v-for="c in chats.data.value.slice(0, 8)" :key="c.conversation_id" type="button" class="hist" @click="openConversation(c)">
          <span>{{ c.turns?.[0]?.q }}</span><span class="muted small">{{ c.started_by }} · {{ fmtDateTime(c.created_at) }}</span>
        </button>
      </section>
      <section class="card stack" v-if="advice.data.value?.usage">
        <h2>{{ t('advisor.usage') }}</h2>
        <p>{{ t('advisor.usageText', { today: advice.data.value.usage.today_calls, cap: advice.data.value.provider.daily_call_cap,
              month: advice.data.value.usage.month_calls, tokens: advice.data.value.usage.month_tokens.toLocaleString() }) }}</p>
        <p class="muted small">{{ advice.data.value.provider.label }} · {{ advice.data.value.provider.model }}</p>
      </section>
    </aside>
  </div>
</template>

<style scoped>
.layout { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(320px, 1fr); gap: 20px; align-items: start; }
.offline { color: var(--warn); background: var(--warn-soft); display: flex; gap: 8px; align-items: center; margin-bottom: 16px; }
.filters { margin-bottom: 4px; }
.seg { display: inline-flex; border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 2px; }
.seg button { min-height: 36px; padding: 0 12px; border: 0; border-radius: 8px; background: transparent; color: var(--ink-2); font: 600 var(--text-sm)/1 var(--font-body); cursor: pointer; }
.seg button.on { background: var(--surface-2); color: var(--ink); box-shadow: 0 0 0 1px var(--line-strong); }
.job { width: auto; }
.small { font-size: 0.8125rem; }
.advice { display: grid; gap: 8px; }
.advice h3 { font-size: var(--text-lg); }
.suggest { background: var(--accent-soft); border-radius: var(--radius); padding: 10px 12px; }
.facts { font-size: 0.8125rem; white-space: pre-wrap; max-height: 240px; overflow: auto; margin: 6px 0 0; }
.decide input { flex: 1; min-width: 180px; }
.chat { display: grid; gap: 10px; }
.chat h2, aside h2 { font-size: var(--text-lg); }
.log { max-height: 460px; overflow-y: auto; display: grid; gap: 10px; padding: 4px 2px; }
.q { justify-self: end; background: var(--accent); color: var(--accent-ink); padding: 8px 12px; border-radius: 14px 14px 4px 14px; max-width: 90%; }
.a { background: var(--surface-2); border: 1px solid var(--line); padding: 10px 12px; border-radius: 14px 14px 14px 4px; max-width: 95%; line-height: 1.5; }
.tools { margin-top: 6px; }
.ask { align-items: flex-end; flex-wrap: nowrap; }
.ask textarea { min-height: 64px; flex: 1; }
.hist { display: grid; text-align: left; gap: 2px; background: transparent; border: 0; border-bottom: 1px solid var(--line); padding: 8px 0; color: var(--ink); cursor: pointer; font: inherit; }
@media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } }
</style>
