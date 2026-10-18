// Network alarm: ping the server every few seconds. If it stays silent longer
// than the alarm timeout (settings.yaml network_alarm.*), raise the alarm.
import { onBeforeUnmount, reactive } from 'vue'

const state = reactive({
  serverOk: true, mongoOk: true, lastOkAt: Date.now(), timeoutSec: 10, intervalSec: 3, sound: true, alarm: false,
})
let timer = null
let users = 0
let audioCtx = null
let beepTimer = null

async function ping() {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), 4000)
  try {
    const res = await fetch('/api/v1/health', { signal: ctrl.signal, cache: 'no-store' })
    const data = await res.json()
    state.lastOkAt = Date.now()
    state.serverOk = true
    state.mongoOk = !!data.mongo
    state.timeoutSec = data.alarm_timeout_seconds || state.timeoutSec
    state.intervalSec = data.heartbeat_interval_seconds || state.intervalSec
    state.sound = data.alarm_sound !== false
  } catch {
    state.serverOk = false
  } finally {
    clearTimeout(t)
  }
  state.alarm = (Date.now() - state.lastOkAt) / 1000 > state.timeoutSec || !state.mongoOk
}

function beep() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)()
    const o = audioCtx.createOscillator()
    const g = audioCtx.createGain()
    o.frequency.value = 880
    g.gain.value = 0.15
    o.connect(g).connect(audioCtx.destination)
    o.start(); o.stop(audioCtx.currentTime + 0.35)
  } catch { /* audio blocked until the first tap; the red screen still shows */ }
}

export function setAlarmSound(on) {
  clearInterval(beepTimer); beepTimer = null
  if (on && state.sound) { beep(); beepTimer = setInterval(beep, 2000) }
}

function loop() {
  ping().finally(() => { timer = setTimeout(loop, state.intervalSec * 1000) })
}

export function useHealth() {
  users += 1
  if (users === 1) loop()
  onBeforeUnmount(() => {
    users -= 1
    if (users === 0) { clearTimeout(timer); setAlarmSound(false) }
  })
  return state
}
