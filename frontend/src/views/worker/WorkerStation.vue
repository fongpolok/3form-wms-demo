<script setup>
// Worker station: one screen, one person, one workstation.
//   1. Device check  (only PIC-registered tablets)
//   2. Staff ID      (type or scan badge; no password)
//   3. Station board (scan batch → Start; Finish / Scrap / Machine stopped / Measure)
// Scrap totals are never shown here. Network problems raise a red alarm and
// actions are kept on this device until the server is reachable again.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ApiError, get, newEventId, post } from '../../api/client.js'
import { fmtDateTime, LANGS, pick, setLang } from '../../i18n/index.js'
import { setAlarmSound, useHealth } from '../../composables/health.js'
import { useSession } from '../../composables/session.js'
import { storage } from '../../composables/storage.js'
import Icon from '../../components/Icon.vue'
import NumPad from '../../components/NumPad.vue'
import ThemeSwitch from '../../components/ThemeSwitch.vue'

const { t, locale } = useI18n()
const session = useSession()
const health = useHealth()

const device = ref(null)          // registered device (workstation)
const deviceError = ref('')
const setupCode = ref('')
const staffId = ref('')
const loginError = ref('')
const board = ref(null)
const toast = ref({ text: '', kind: 'ok' })
const busy = ref(false)
const muted = ref(false)
const pending = ref(storage.local.getJSON('pendingActions', []))
const sheet = ref(null)           // 'finish' | 'scrap' | 'stop' | 'measure' | 'fix'
const dialogEl = ref(null)
const form = ref({ qty: '', reason: '', note: '', value: '' })

let pollTimer = null
const POLL_MS = 1000   // matches settings.yaml network_alarm.worker_poll_interval_ms
let lastScanTs = null

const ws = computed(() => device.value?.workstation)
const loggedIn = computed(() => session.isLoggedIn.value && !!storage.session.get('token'))
const current = computed(() => board.value?.current)
const step = computed(() => board.value?.workstation)
const scannerProblems = computed(() => (board.value?.health || []).filter((d) => d.kind !== 'gateway' && !d.ok))
const alarm = computed(() => health.alarm || (loggedIn.value && scannerProblems.value.length > 0))

watch(alarm, (on) => setAlarmSound(on && !muted.value))
watch(muted, (m) => setAlarmSound(alarm.value && !m))

function flash(text, kind = 'ok') {
  toast.value = { text, kind }
  setTimeout(() => { if (toast.value.text === text) toast.value = { text: '', kind: 'ok' } }, 4000)
}

// ---------------------------------------------------------------- device
async function checkDevice() {
  if (!storage.local.get('deviceToken')) { device.value = null; return }
  try {
    device.value = await get('/api/v1/devices/current')
    deviceError.value = ''
  } catch (e) {
    if (e.status === 403) { storage.local.remove('deviceToken'); device.value = null }
    deviceError.value = e.message
  }
}

function useSetupCode() {
  storage.local.set('deviceToken', setupCode.value.trim())
  setupCode.value = ''
  checkDevice()
}

// ---------------------------------------------------------------- login
async function login(id = staffId.value) {
  if (!id) return
  loginError.value = ''
  busy.value = true
  try {
    await session.workerLogin(String(id).trim())
    staffId.value = ''
    await loadBoard()
  } catch (e) {
    loginError.value = e.message
  } finally {
    busy.value = false
  }
}

async function endShift() {
  await session.logout()
  board.value = null
}

// ---------------------------------------------------------------- board + scans
async function loadBoard() {
  if (!loggedIn.value || !ws.value) return
  try {
    board.value = await get(`/api/v1/mes/workstations/${ws.value}/board`)
  } catch (e) {
    if (e.status === 401) board.value = null
  }
}

async function pollScans() {
  if (!ws.value) return
  try {
    const q = lastScanTs ? `?after=${encodeURIComponent(lastScanTs)}` : ''
    const scans = await get(`/api/v1/mes/workstations/${ws.value}/scans${q}`)
    if (!lastScanTs) { lastScanTs = scans[0]?.ts || new Date().toISOString(); return } // ignore history
    if (!scans.length) return
    lastScanTs = scans[0].ts
    for (const s of scans.reverse()) handleScan(s.code)
  } catch { /* the health check raises the alarm */ }
}

function handleScan(code) {
  if (!loggedIn.value) {
    if (!/^(B|WIP|WO)-/.test(code)) login(code)   // badge scan
    return
  }
  if (board.value?.putaway && !/^(B|WIP|WO)-/.test(code)) return act('putaway', { bin: code })
  if (code.startsWith('B-')) {
    if (current.value?.batch_id === code) return flash(`${code} · ${t('worker.started')}`)
    if (current.value) return flash(t('worker.current') + `: ${current.value.batch_id}`, 'warn')
    act('start', { batch_id: code })
  }
}

async function tick() {
  if (health.serverOk) await flushPending()
  await pollScans()
  if (loggedIn.value) await loadBoard()
}

// ---------------------------------------------------------------- actions
function savePending() { storage.local.setJSON('pendingActions', pending.value) }

async function send(item) {
  return post(`/api/v1/mes/workstations/${item.ws}/${item.action}`, item.body)
}

async function flushPending() {
  while (pending.value.length) {
    try {
      await send(pending.value[0])
    } catch (e) {
      if (e.status === 0) return          // still offline
      flash(e.message, 'alarm')           // refused: drop it, tell the worker
    }
    pending.value.shift()
    savePending()
  }
}

const doneText = { start: 'worker.started', finish: 'worker.finished', scrap: 'worker.recorded',
                   stop: 'worker.stopped', resume: 'worker.resumed', measure: 'worker.recorded', putaway: 'worker.putDone' }

async function act(action, body = {}) {
  const item = { ws: ws.value, action, body: { ...body, event_id: newEventId(), client_ts: new Date().toISOString() } }
  busy.value = true
  try {
    const res = await send(item)
    if (action === 'measure' && res.in_spec === false) flash(`${t('worker.recorded')} · ⚠ ${t('worker.target')}`, 'warn')
    else if (action === 'finish' && res.putaway) flash(t('worker.nowPutAway', { bin: res.suggested_bin || '—' }))
    else if (action === 'putaway') flash(t('worker.putDone', { bin: res.bin_name }))
    else flash(t(doneText[action]))
    closeSheet()
    await loadBoard()
  } catch (e) {
    if (e instanceof ApiError && e.status === 0) {
      pending.value.push(item); savePending()
      flash(t('worker.queued'), 'warn')
      closeSheet()
    } else {
      flash(e.message, 'alarm')
    }
  } finally {
    busy.value = false
  }
}

function openSheet(name) {
  form.value = { qty: name === 'finish' ? String(current.value?.expected_good ?? current.value?.qty_in ?? 0) : '', reason: '', note: '', value: '' }
  sheet.value = name
  requestAnimationFrame(() => dialogEl.value?.showModal())
}
function closeSheet() { dialogEl.value?.close(); sheet.value = null }

function submitSheet() {
  const f = form.value
  if (sheet.value === 'finish') act('finish', { good_qty: Number(f.qty || 0) })
  if (sheet.value === 'scrap') act('scrap', { qty: Number(f.qty || 0), reason_code: f.reason, note: f.note })
  if (sheet.value === 'stop') act('stop', { reason_code: f.reason, note: f.note })
  if (sheet.value === 'measure') act('measure', { value: f.value })
}

const sheetReady = computed(() => {
  const f = form.value
  if (sheet.value === 'finish') return f.qty !== ''
  if (sheet.value === 'scrap') return Number(f.qty) > 0 && f.reason && (f.reason !== 'OTHER' || f.note.trim())
  if (sheet.value === 'stop') return !!f.reason
  if (sheet.value === 'measure') return f.value !== ''
  return true
})

onMounted(async () => {
  await checkDevice()
  if (loggedIn.value) await loadBoard()
  const loop = async () => {
    await tick()
    pollTimer = setTimeout(loop, POLL_MS)
  }
  loop()
})
onBeforeUnmount(() => { clearTimeout(pollTimer); setAlarmSound(false) })
</script>

<template>
  <div class="ws" :class="{ alarm }">
    <!-- ============ Network alarm (colour + words + icon) ============ -->
    <div v-if="alarm" class="alarm-bar" role="alert">
      <Icon name="alert" :size="32" />
      <div class="grow">
        <strong>{{ t('alarm.title') }}</strong>
        <p v-if="!health.serverOk">{{ t('alarm.serverDown') }}</p>
        <p v-else-if="!health.mongoOk">{{ t('alarm.db') }}</p>
        <p v-for="d in scannerProblems" :key="d.device_id">{{ t('alarm.deviceDown', { id: d.device_id }) }}</p>
        <p>{{ t('alarm.keepWorking') }}</p>
      </div>
      <button class="btn" @click="openSheet('fix')">{{ t('alarm.fix') }}</button>
      <button class="btn btn-quiet" @click="muted = !muted" :aria-pressed="muted">{{ t('alarm.mute') }}</button>
    </div>

    <!-- ============ 1. Not a registered device ============ -->
    <section v-if="!device" class="center card stack">
      <img src="/brand/logo.png" alt="3Form" width="64" height="64" class="logo" />
      <h1>{{ t('worker.notRegistered') }}</h1>
      <p class="muted big">{{ t('worker.notRegisteredHelp') }}</p>
      <p v-if="deviceError" class="notice notice-error">{{ deviceError }}</p>
      <form class="row" @submit.prevent="useSetupCode">
        <label class="field grow"><span>Setup code</span><input v-model="setupCode" autocomplete="off" /></label>
        <button class="btn btn-primary" :disabled="!setupCode">OK</button>
      </form>
      <RouterLink to="/login">{{ t('login.title') }}</RouterLink>
    </section>

    <!-- ============ 2. Staff ID ============ -->
    <section v-else-if="!loggedIn || !board" class="center card stack login">
      <div class="row">
        <span class="pill pill-info"><Icon name="station" :size="16" /> {{ device.workstation }}</span>
        <span class="spacer"></span>
        <ThemeSwitch />
        <select :value="locale" @change="setLang($event.target.value)" class="lang" :aria-label="t('common.language')">
          <option v-for="l in LANGS" :key="l.code" :value="l.code">{{ l.label }}</option>
        </select>
      </div>
      <h1>{{ t('worker.enterStaffId') }}</h1>
      <label class="field">
        <span>{{ t('worker.staffId') }}</span>
        <input class="huge" v-model="staffId" inputmode="numeric" autocomplete="off" @keyup.enter="login()" />
      </label>
      <NumPad v-model="staffId" />
      <p v-if="loginError" class="notice notice-error" role="alert">{{ loginError }}</p>
      <button class="btn btn-primary xl" :disabled="!staffId || busy" @click="login()">{{ t('worker.go') }}</button>
    </section>

    <!-- ============ 3. Station board ============ -->
    <template v-else>
      <header class="head">
        <div>
          <p class="eyebrow">{{ t('worker.station') }} {{ step.code }}</p>
          <h1>{{ pick(step.step_name) }}</h1>
        </div>
        <span class="spacer"></span>
        <span :class="['pill', health.serverOk ? 'pill-ok' : 'pill-alarm']">
          <Icon :name="health.serverOk ? 'check' : 'x'" :size="16" /> {{ health.serverOk ? t('common.online') : t('common.offline') }}
        </span>
        <span v-if="pending.length" class="pill pill-warn">{{ t('worker.pendingSend', { n: pending.length }) }}</span>
        <div class="who"><strong>{{ session.state.account?.display_name }}</strong><span class="muted">#{{ session.state.account?.staff_id }}</span></div>
        <button class="btn" @click="endShift"><Icon name="out" :size="18" /> {{ t('worker.endShift') }}</button>
      </header>

      <p v-if="toast.text" :class="['toast', `toast-${toast.kind}`]" role="status" aria-live="polite">{{ toast.text }}</p>

      <!-- Running batch -->
      <section v-if="current" class="card now" :class="{ stopped: current.machine_stopped }">
        <div class="row">
          <div class="grow">
            <p class="eyebrow">{{ t('worker.current') }}</p>
            <h2 class="mono">{{ current.batch_id }}</h2>
            <p class="big">{{ current.product_name }} · {{ t('worker.qtyIn') }}: <strong>{{ current.qty_in }}</strong></p>
            <p class="muted mono">{{ current.wip_id }}</p>
          </div>
          <span v-if="current.machine_stopped" class="pill pill-alarm big-pill"><Icon name="pause" :size="20" /> {{ t('worker.machineStopped') }}</span>
        </div>
        <div class="actions">
          <button class="act act-primary" :disabled="busy || current.machine_stopped" @click="openSheet('finish')">
            <Icon name="check" :size="36" /> {{ t('worker.finish') }}
          </button>
          <button class="act" :disabled="busy" @click="openSheet('scrap')"><Icon name="trash" :size="36" /> {{ t('worker.scrap') }}</button>
          <button v-if="!current.machine_stopped" class="act act-warn" :disabled="busy" @click="openSheet('stop')">
            <Icon name="pause" :size="36" /> {{ t('worker.stop') }}
          </button>
          <button v-else class="act act-primary" :disabled="busy" @click="act('resume')"><Icon name="play" :size="36" /> {{ t('worker.resume') }}</button>
          <button v-if="step.measurement" class="act" :disabled="busy" @click="openSheet('measure')">
            <Icon name="ruler" :size="36" /> {{ t('worker.measure') }}
          </button>
        </div>
      </section>

      <!-- Put away a finished batch (QC station, order goes to stock) -->
      <section v-else-if="board.putaway" class="card stack putaway">
        <p class="eyebrow">{{ t('worker.putAway') }}</p>
        <h2 class="mono">{{ board.putaway.batch_id }}</h2>
        <p class="big">{{ board.putaway.product_name }} · {{ board.putaway.good_qty_out }} pcs</p>
        <div class="row"><Icon name="scan" :size="28" /><p class="big">{{ t('worker.scanBin') }}</p></div>
        <button v-if="board.putaway.suggested_bin" class="act act-primary" :disabled="busy"
                @click="act('putaway', { bin: board.putaway.suggested_bin })">
          <Icon name="box" :size="36" /> {{ t('worker.putInto', { bin: board.putaway.suggested_bin }) }}
        </button>
      </section>

      <!-- Queue -->
      <section v-else class="card stack">
        <div class="row"><Icon name="scan" :size="28" /><h2>{{ t('worker.scanBatch') }}</h2></div>
        <p v-if="!board.queue.length" class="muted big">{{ t('worker.noneWaiting') }}</p>
        <ul class="queue">
          <li v-for="b in board.queue" :key="b.batch_id">
            <div class="grow">
              <strong class="mono">{{ b.batch_id }}</strong>
              <span v-if="b.special_urgent" class="pill pill-alarm"><Icon name="alert" :size="14" /> {{ t('worker.urgent') }}</span>
              <span v-if="b.waiting_material" class="pill pill-warn"><Icon name="pause" :size="14" /> {{ t('wo.waitingMaterial') }}</span>
              <p class="muted">{{ b.product_name }} · {{ b.last_good_qty ?? b.qty }} pcs
                <template v-if="b.planned_start"> · {{ t('plan.plannedStart') }} {{ fmtDateTime(b.planned_start) }}</template></p>
            </div>
            <button class="act act-primary small" :disabled="busy || b.waiting_material" @click="act('start', { batch_id: b.batch_id })">
              <Icon name="play" :size="28" /> {{ t('worker.start') }}
            </button>
          </li>
        </ul>
      </section>
    </template>

    <!-- ============ Sheets ============ -->
    <dialog ref="dialogEl" class="sheet" @close="sheet = null" aria-labelledby="sheet-title">
      <form v-if="sheet" method="dialog" class="stack" @submit.prevent="submitSheet">
        <template v-if="sheet === 'finish'">
          <h2 id="sheet-title">{{ t('worker.goodQty') }}</h2>
          <input class="huge" v-model="form.qty" inputmode="numeric" />
          <NumPad v-model="form.qty" :max-length="6" />
        </template>

        <template v-else-if="sheet === 'scrap'">
          <h2 id="sheet-title">{{ t('worker.whyScrap') }}</h2>
          <div class="choices" role="radiogroup">
            <button v-for="r in board.scrap_reasons" :key="r.code" type="button" role="radio"
                    :aria-checked="form.reason === r.code" :class="['choice', { on: form.reason === r.code }]"
                    @click="form.reason = r.code">{{ pick(r) }}</button>
          </div>
          <label v-if="form.reason === 'OTHER'" class="field"><span>{{ t('worker.note') }}</span><input v-model="form.note" /></label>
          <label class="field"><span>{{ t('worker.scrapQty') }}</span><input class="huge" v-model="form.qty" inputmode="numeric" /></label>
          <NumPad v-model="form.qty" :max-length="6" />
        </template>

        <template v-else-if="sheet === 'stop'">
          <h2 id="sheet-title">{{ t('worker.whyStop') }}</h2>
          <div class="choices" role="radiogroup">
            <button v-for="r in board.downtime_reasons" :key="r.code" type="button" role="radio"
                    :aria-checked="form.reason === r.code" :class="['choice', { on: form.reason === r.code }]"
                    @click="form.reason = r.code">{{ pick(r) }}</button>
          </div>
        </template>

        <template v-else-if="sheet === 'measure'">
          <h2 id="sheet-title">{{ step.measurement.name }} ({{ step.measurement.unit }})</h2>
          <p class="muted big">{{ t('worker.target') }}: {{ step.measurement.target }} {{ step.measurement.unit }}</p>
          <input class="huge" v-model="form.value" inputmode="decimal" />
          <NumPad v-model="form.value" :max-length="8" decimal />
        </template>

        <template v-else-if="sheet === 'fix'">
          <h2 id="sheet-title">{{ t('alarm.fix') }}</h2>
          <ol class="fix big">
            <li>{{ t('alarm.check1') }}</li><li>{{ t('alarm.check2') }}</li><li>{{ t('alarm.check3') }}</li>
          </ol>
        </template>

        <div class="row sheet-actions">
          <button type="button" class="btn xl" @click="closeSheet">{{ sheet === 'fix' ? t('common.close') : t('common.cancel') }}</button>
          <button v-if="sheet !== 'fix'" class="btn btn-primary xl grow" :disabled="!sheetReady || busy">{{ t('common.save') }}</button>
        </div>
      </form>
    </dialog>
  </div>
</template>

<style scoped>
.ws { min-height: 100vh; padding: 20px; display: grid; gap: 20px; align-content: start; font-size: var(--text-lg);
      max-width: 1100px; margin: 0 auto; }
.ws.alarm { box-shadow: inset 0 0 0 8px #b91c1c; }
.center { max-width: 560px; width: 100%; margin: 6vh auto 0; padding: 32px; }
.login h1 { font-size: var(--text-xl); }
.logo { border-radius: 14px; }
.big { font-size: var(--text-lg); }
.grow { flex: 1; min-width: 0; }
.lang { width: auto; }
.eyebrow { font-size: var(--text-sm); font-weight: 650; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-2); }
.head { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.head h1 { font-size: 2.5rem; }
.who { display: grid; line-height: 1.2; text-align: right; }
.huge { font-size: 2rem; min-height: 72px; text-align: center; font-weight: 650; letter-spacing: 0.08em; }
.xl { min-height: var(--tap-worker); font-size: var(--text-lg); padding: 0 28px; }

.alarm-bar { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; padding: 16px 20px; border-radius: var(--radius-lg);
             background: #b91c1c; color: #fff; }   /* fixed in both themes: white on #B91C1C = 6.5:1 */
.alarm-bar .btn { background: #fff; color: #7f1d1d; border-color: #fff; }
.alarm-bar .btn-quiet { background: transparent; color: #fff; }
@media (prefers-reduced-motion: no-preference) { .alarm-bar { animation: pulse 1.6s ease-in-out infinite; } }
@keyframes pulse { 50% { filter: brightness(1.15); } }

.toast { padding: 14px 18px; border-radius: var(--radius); font-weight: 650; border: 1px solid; }
.toast-ok { color: var(--ok); background: var(--ok-soft); }
.toast-warn { color: var(--warn); background: var(--warn-soft); }
.toast-alarm { color: var(--alarm); background: var(--alarm-soft); }

.now h2 { font-size: 2rem; margin: 4px 0; }
.now.stopped { border-color: var(--alarm); border-width: 3px; }
.big-pill { font-size: var(--text-lg); padding: 8px 16px; }
.actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 24px; }
.act { min-height: 128px; display: grid; place-items: center; align-content: center; gap: 10px; border-radius: 18px; cursor: pointer;
       border: 2px solid var(--line-strong); background: var(--surface); color: var(--ink); font: 700 1.375rem/1.1 var(--font-body); }
.act:disabled { opacity: 0.4; cursor: not-allowed; }
.act-primary { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
.act-warn { border-color: var(--warn); color: var(--warn); }
.act.small { min-height: var(--tap-worker); min-width: 180px; display: flex; justify-content: center; gap: 12px; }

.putaway { border-color: var(--accent); border-width: 2px; }
.putaway h2 { font-size: 2rem; }
.queue { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
.queue li { display: flex; gap: 16px; align-items: center; padding: 16px; border: 1px solid var(--line); border-radius: var(--radius-lg); }
.queue strong { font-size: 1.375rem; margin-right: 8px; }

.sheet { width: min(640px, calc(100vw - 32px)); max-height: calc(100vh - 32px); border: 0; border-radius: 20px; padding: 28px;
         background: var(--surface); color: var(--ink); }
.sheet::backdrop { background: rgb(0 26 74 / 0.55); }
.choices { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.choice { min-height: 72px; border-radius: 14px; border: 2px solid var(--line-strong); background: var(--surface);
          color: var(--ink); font: 600 var(--text-lg)/1.2 var(--font-body); cursor: pointer; padding: 8px; }
.choice.on { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
.choice.on::before { content: '✓ '; }
.sheet-actions { margin-top: 8px; }
.fix { display: grid; gap: 12px; padding-left: 1.4em; }
</style>
