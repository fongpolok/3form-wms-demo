<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, post } from '../../api/client.js'
import { useSession } from '../../composables/session.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import Icon from '../../components/Icon.vue'

const { t } = useI18n()
const session = useSession()
const { data, error, reload } = usePolled(() => get('/api/v1/mes/work-orders'), 15000)
const blank = () => ({ product_code: '', product_name: '', client: '', qty: 100, batches: 1, due_date: '', ship_mode: 'stock', client_priority: 3 })
const form = ref(blank())
const msg = ref({ text: '', kind: 'ok' })
const busy = ref(false)

async function create() {
  busy.value = true
  try {
    const res = await post('/api/v1/mes/work-orders', form.value)
    msg.value = { text: t('wo.created', { id: res.work_order.wo_id }), kind: 'ok' }
    form.value = blank()
    reload()
  } catch (e) {
    msg.value = { text: e.message, kind: 'error' }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <PageHead :title="t('wo.title')" />
  <section v-if="session.can('PIC')" class="card stack new">
    <h2>{{ t('wo.new') }}</h2>
    <form class="form" @submit.prevent="create">
      <label class="field"><span>{{ t('wo.product') }}</span><input v-model="form.product_code" required /></label>
      <label class="field"><span>{{ t('wo.productName') }}</span><input v-model="form.product_name" /></label>
      <label class="field"><span>{{ t('wo.client') }}</span><input v-model="form.client" /></label>
      <label class="field"><span>{{ t('wo.qty') }}</span><input v-model.number="form.qty" type="number" min="1" required /></label>
      <label class="field"><span>{{ t('wo.batches') }}</span><input v-model.number="form.batches" type="number" min="1" required /></label>
      <label class="field"><span>{{ t('wo.due') }}</span><input v-model="form.due_date" type="date" required /></label>
      <label class="field"><span>{{ t('wo.priority') }}</span>
        <select v-model.number="form.client_priority"><option v-for="p in 5" :key="p" :value="p">{{ p }}</option></select></label>
      <fieldset class="field">
        <span>{{ t('wo.shipMode') }}</span>
        <label class="radio"><input type="radio" value="stock" v-model="form.ship_mode" /> {{ t('wo.stock') }}</label>
        <label class="radio"><input type="radio" value="direct" v-model="form.ship_mode" /> {{ t('wo.direct') }}</label>
      </fieldset>
      <div class="row full">
        <button class="btn btn-primary" :disabled="busy">{{ t('wo.create') }}</button>
        <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>
      </div>
    </form>
  </section>
  <p v-else class="muted">{{ t('wo.viewOnly') }}</p>

  <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
  <div class="card table-wrap">
    <table class="table">
      <thead><tr><th>WO</th><th>{{ t('wo.productName') }}</th><th>{{ t('wo.client') }}</th><th>{{ t('wo.qty') }}</th>
        <th>{{ t('wo.due') }}</th><th>{{ t('wo.shipMode') }}</th><th>{{ t('wo.source') }}</th><th>{{ t('common.status') }}</th></tr></thead>
      <tbody>
        <tr v-for="w in data" :key="w.wo_id">
          <td class="mono">{{ w.wo_id }}
            <span v-if="w.special_urgent" class="pill pill-alarm"><Icon name="alert" :size="12" /> {{ t('progress.urgent') }}</span></td>
          <td>{{ w.product_name || w.product_code }}</td><td>{{ w.client }}</td><td>{{ w.qty }}</td><td>{{ w.due_date }}</td>
          <td>{{ w.ship_mode === 'stock' ? t('wo.stock') : t('wo.direct') }}</td><td>{{ w.source }}</td>
          <td><span v-if="w.status === 'waiting_material'" class="pill pill-warn" :title="w.shortages.map((s) => `${s.goods_code} -${s.short}`).join(', ')">
            <Icon name="alert" :size="12" /> {{ t('wo.waitingMaterial') }}</span>
            <span v-else>{{ t(`wo.status.${w.status}`) }}</span>
            <div v-if="w.shortages?.length" class="muted short">{{ w.shortages.map((s) => `${s.goods_code} −${s.short}`).join(', ') }}</div></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.new { margin-bottom: 24px; }
.form { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.full { grid-column: 1 / -1; }
fieldset { border: 0; padding: 0; margin: 0; }
.radio { display: flex; gap: 8px; align-items: center; min-height: 36px; }
.radio input { width: auto; min-height: auto; }
.short { font-size: 0.8125rem; }
</style>
