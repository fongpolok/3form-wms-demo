<script setup>
// Working calendar for the APS: shifts + breaks, working days, holidays,
// and staffing changes per date. PIC edits; Engineering Manager reads.
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { del, get, post, put } from '../../api/client.js'
import { useSession } from '../../composables/session.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'

const { t } = useI18n()
const session = useSession()
const cal = usePolled(() => get('/api/v1/aps/calendar'), 0)
const shifts = ref([])
const days = ref([])
const msg = ref({ text: '', kind: 'ok' })
const hol = ref({ date: '', name: '' })
const staff = ref({ date: '', shift_code: 'A', workers: 6, note: '' })
const DAY = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
watch(() => cal.data.value, (v) => { if (v) { shifts.value = JSON.parse(JSON.stringify(v.shifts)); days.value = [...v.working_days] } }, { immediate: true })

function toggleDay(i) { days.value = days.value.includes(i) ? days.value.filter((d) => d !== i) : [...days.value, i].sort() }
const ok = (text) => { msg.value = { kind: 'ok', text } }
const fail = (e) => { msg.value = { kind: 'error', text: e.message } }
async function saveShifts() { try { await put('/api/v1/aps/calendar', { shifts: shifts.value, working_days: days.value }); ok(t('calendar.saved')); cal.reload() } catch (e) { fail(e) } }
async function addHoliday() { try { await post('/api/v1/aps/holidays', hol.value); hol.value = { date: '', name: '' }; ok(t('calendar.saved')); cal.reload() } catch (e) { fail(e) } }
async function removeHoliday(d) { try { await del(`/api/v1/aps/holidays/${d}`); cal.reload() } catch (e) { fail(e) } }
async function addStaff() { try { await post('/api/v1/aps/staffing', staff.value); ok(t('calendar.saved')); cal.reload() } catch (e) { fail(e) } }
</script>

<template>
  <PageHead :title="t('nav.calendar')" :subtitle="session.can('PIC') ? t('calendar.subtitle') : t('calendar.readOnly')" />
  <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>
  <fieldset :disabled="!session.can('PIC')" class="plain">
    <section class="card stack">
      <h2>{{ t('calendar.shifts') }}</h2>
      <div class="table-wrap"><table class="table">
        <thead><tr><th>{{ t('calendar.code') }}</th><th>{{ t('calendar.start') }}</th><th>{{ t('calendar.end') }}</th><th>{{ t('calendar.break') }}</th><th>{{ t('calendar.breakMin') }}</th><th>{{ t('calendar.workers') }}</th></tr></thead>
        <tbody><tr v-for="s in shifts" :key="s.code">
          <td class="mono">{{ s.code }}</td><td><input v-model="s.start" type="time" /></td><td><input v-model="s.end" :type="s.end === '24:00' ? 'text' : 'time'" /></td>
          <td><input v-model="s.break_start" type="time" /></td><td><input v-model.number="s.break_minutes" type="number" min="0" /></td>
          <td><input v-model.number="s.workers" type="number" min="0" /></td></tr></tbody>
      </table></div>
      <div class="row days" role="group" :aria-label="t('calendar.workingDays')">
        <span class="muted">{{ t('calendar.workingDays') }}:</span>
        <label v-for="(d, i) in DAY" :key="d" class="chk"><input type="checkbox" :checked="days.includes(i)" @change="toggleDay(i)" /> {{ t(`calendar.day.${d}`) }}</label>
      </div>
      <div><button class="btn btn-primary" @click="saveShifts">{{ t('common.save') }}</button></div>
    </section>

    <div class="grid2">
      <section class="card stack">
        <h2>{{ t('calendar.holidays') }}</h2>
        <form class="row add" @submit.prevent="addHoliday">
          <label class="field"><span>{{ t('calendar.date') }}</span><input v-model="hol.date" type="date" required /></label>
          <label class="field grow"><span>{{ t('calendar.name') }}</span><input v-model="hol.name" /></label>
          <button class="btn">{{ t('calendar.add') }}</button>
        </form>
        <ul class="list">
          <li v-for="h in cal.data.value?.holidays || []" :key="h.date"><span class="mono">{{ h.date }}</span> {{ h.name }}
            <span class="muted">({{ h.source }})</span>
            <button v-if="session.can('PIC')" type="button" class="btn btn-quiet tiny" @click="removeHoliday(h.date)" :aria-label="`${t('products.remove')} ${h.date}`">✕</button></li>
        </ul>
      </section>
      <section class="card stack">
        <h2>{{ t('calendar.staffing') }}</h2>
        <p class="muted">{{ t('calendar.staffingHelp') }}</p>
        <form class="row add" @submit.prevent="addStaff">
          <label class="field"><span>{{ t('calendar.date') }}</span><input v-model="staff.date" type="date" required /></label>
          <label class="field"><span>{{ t('calendar.code') }}</span><select v-model="staff.shift_code"><option v-for="s in shifts" :key="s.code">{{ s.code }}</option></select></label>
          <label class="field"><span>{{ t('calendar.workers') }}</span><input v-model.number="staff.workers" type="number" min="0" required /></label>
          <button class="btn">{{ t('common.save') }}</button>
        </form>
        <ul class="list">
          <li v-for="s in cal.data.value?.staffing || []" :key="s.id"><span class="mono">{{ s.date }} {{ s.shift_code }}</span> · {{ s.workers }} {{ t('calendar.people') }} <span class="muted">{{ s.note }}</span></li>
          <li v-if="!(cal.data.value?.staffing || []).length" class="muted">{{ t('common.none') }}</li>
        </ul>
      </section>
    </div>
  </fieldset>
  <section v-if="cal.data.value" class="card block">
    <h2>{{ t('calendar.rules') }}</h2>
    <p class="muted">{{ t('calendar.rulesText', cal.data.value.settings) }}</p>
  </section>
</template>

<style scoped>
.plain { border: 0; padding: 0; margin: 0; min-width: 0; }
.stack h2, .block h2 { font-size: var(--text-lg); }
.table input { min-height: 38px; }
.days { gap: 14px; }
.chk { display: flex; gap: 6px; align-items: center; }
.chk input { width: auto; min-height: auto; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; margin-top: 16px; }
.add { align-items: flex-end; }
.grow { flex: 1; }
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; max-height: 320px; overflow-y: auto; font-size: var(--text-sm); }
.list li { display: flex; gap: 8px; align-items: center; }
.list .mono { white-space: nowrap; }
.tiny { min-height: 28px; padding: 0 8px; }
.block { margin-top: 16px; }
</style>
