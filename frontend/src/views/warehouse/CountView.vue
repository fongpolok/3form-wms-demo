<script setup>
// Cycle count: count a lot in a bin; a difference waits for the PIC to approve.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, post } from '../../api/client.js'
import { useSession } from '../../composables/session.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'

const { t } = useI18n()
const session = useSession()
const bins = usePolled(() => get('/api/v1/inventory/bins'), 0)
const tasks = usePolled(() => get('/api/v1/inventory/counts'), 15000)
const bin = ref('')
const pickLot = ref(null)
const counted = ref('')
const msg = ref({ text: '', kind: 'ok' })
const contents = computed(() => (bins.data.value?.bins || []).find((b) => b.bin_name === bin.value)?.contents || [])

async function submit() {
  try {
    const r = await post('/api/v1/inventory/counts', { bin_name: bin.value, goods_code: pickLot.value.goods_code,
                                                        lot_number: pickLot.value.lot_number, counted_qty: counted.value })
    msg.value = { kind: 'ok', text: r.variance === 0 ? t('count.match') : t('count.variance', { v: r.variance }) }
    counted.value = ''; tasks.reload(); bins.reload()
  } catch (e) { msg.value = { kind: 'error', text: e.message } }
}
async function decide(task, approve) {
  try { await post(`/api/v1/inventory/counts/${task.id}/decision`, { approve }); tasks.reload(); bins.reload() }
  catch (e) { msg.value = { kind: 'error', text: e.message } }
}
</script>

<template>
  <PageHead :title="t('nav.count')" :subtitle="t('count.subtitle')" />
  <form class="card form" @submit.prevent="submit">
    <label class="field"><span>{{ t('stock.bin') }}</span>
      <select v-model="bin" @change="pickLot = null"><option value="" disabled>—</option>
        <option v-for="b in bins.data.value?.bins || []" :key="b.bin_name" :value="b.bin_name">{{ b.bin_name }} ({{ b.contents.length }})</option></select></label>
    <label class="field"><span>{{ t('count.item') }}</span>
      <select v-model="pickLot" :disabled="!contents.length"><option :value="null" disabled>—</option>
        <option v-for="c in contents" :key="c.goods_code + c.lot_number" :value="c">{{ c.goods_code }} · {{ c.lot_number || '–' }}</option></select></label>
    <label class="field"><span>{{ t('count.counted') }}</span><input v-model.number="counted" type="number" min="0" required /></label>
    <div class="row full">
      <button class="btn btn-primary" :disabled="!pickLot || counted === ''">{{ t('count.submit') }}</button>
      <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>
    </div>
  </form>
  <section class="card table-wrap block">
    <table class="table"><thead><tr><th>Time</th><th>{{ t('stock.bin') }}</th><th>{{ t('count.item') }}</th><th>{{ t('count.system') }}</th>
      <th>{{ t('count.counted') }}</th><th>±</th><th>{{ t('common.status') }}</th><th></th></tr></thead>
      <tbody><tr v-for="c in tasks.data.value || []" :key="c.id"><td>{{ $dt(c.created_at) }}</td><td class="mono">{{ c.bin_name }}</td>
        <td class="mono">{{ c.goods_code }} {{ c.lot_number }}</td><td>{{ c.system_qty }}</td><td>{{ c.counted_qty }}</td>
        <td :class="{ neg: c.variance < 0 }">{{ c.variance > 0 ? '+' : '' }}{{ c.variance }}</td>
        <td><span :class="['pill', c.status === 'pending' ? 'pill-warn' : c.status === 'approved' ? 'pill-ok' : 'pill-alarm']">
          <Icon :name="c.status === 'approved' ? 'check' : c.status === 'pending' ? 'alert' : 'x'" :size="12" /> {{ t(`count.${c.status}`) }}</span></td>
        <td class="row"><template v-if="c.status === 'pending' && session.can('PIC')">
          <button class="btn" @click="decide(c, true)">{{ t('count.approve') }}</button><button class="btn" @click="decide(c, false)">{{ t('count.reject') }}</button></template></td></tr></tbody></table>
  </section>
</template>

<style scoped>
.form { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.full { grid-column: 1 / -1; }
.block { margin-top: 20px; }
.neg { color: var(--alarm); font-weight: 700; }
</style>
