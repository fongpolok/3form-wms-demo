<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, patch, post } from '../../api/client.js'
import { useSession } from '../../composables/session.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'

const { t } = useI18n()
const session = useSession()
const { data, reload, error } = usePolled(() => get('/api/v1/inventory/bins'), 20000)
const zoneFilter = ref('')
const form = ref({ bin_name: '', zone: 'RAW' })
const msg = ref({ text: '', kind: 'ok' })
const bins = computed(() => (data.value?.bins || []).filter((b) => !zoneFilter.value || b.zone === zoneFilter.value))

async function add() {
  try { await post('/api/v1/inventory/bins', form.value); msg.value = { kind: 'ok', text: `${form.value.bin_name} ✓` }; form.value.bin_name = ''; reload() }
  catch (e) { msg.value = { kind: 'error', text: e.message } }
}
async function setZone(b, zone) {
  try { await patch(`/api/v1/inventory/bins/${encodeURIComponent(b.bin_name)}/zone`, { zone }); reload() }
  catch (e) { msg.value = { kind: 'error', text: e.message } }
}
</script>

<template>
  <PageHead :title="t('nav.bins')" :subtitle="t('bins.subtitle', { fg: data?.suggested_fg_bin || '–' })" />
  <form v-if="session.can('PIC')" class="card row add" @submit.prevent="add">
    <label class="field"><span>{{ t('stock.bin') }}</span><input v-model="form.bin_name" required class="mono" /></label>
    <label class="field"><span>Zone</span><select v-model="form.zone"><option v-for="z in data?.zones || []" :key="z[0]" :value="z[0]">{{ z[1] }}</option></select></label>
    <button class="btn btn-primary">{{ t('bins.add') }}</button>
    <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']">{{ msg.text }}</p>
  </form>
  <p v-if="error" class="notice notice-error">{{ error }}</p>
  <div class="row filter">
    <label class="field"><span>Zone</span><select v-model="zoneFilter"><option value="">All</option><option v-for="z in data?.zones || []" :key="z[0]" :value="z[0]">{{ z[1] }}</option></select></label>
  </div>
  <div class="grid">
    <article v-for="b in bins" :key="b.bin_name" :class="['card', 'bin', { empty: !b.contents.length }]">
      <div class="row"><strong class="mono grow">{{ b.bin_name }}</strong>
        <select v-if="session.can('PIC')" :value="b.zone" @change="setZone(b, $event.target.value)" :aria-label="`${b.bin_name} zone`" class="zone">
          <option v-for="z in data?.zones || []" :key="z[0]" :value="z[0]">{{ z[0] }}</option></select>
        <span v-else class="pill pill-info">{{ b.zone }}</span></div>
      <p v-if="!b.contents.length" class="muted">{{ t('bins.empty') }}</p>
      <ul v-else><li v-for="c in b.contents" :key="c.goods_code + c.lot_number" class="mono">{{ c.goods_code }} · {{ c.lot_number || '–' }} · {{ c.qty.toLocaleString() }}</li></ul>
    </article>
  </div>
</template>

<style scoped>
.add, .filter { align-items: flex-end; margin-bottom: 16px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
.bin { padding: 14px 16px; display: grid; gap: 8px; align-content: start; }
.bin.empty { background: var(--surface-2); }
.grow { flex: 1; }
.zone { min-height: 34px; width: auto; padding: 2px 8px; }
ul { margin: 0; padding-left: 1.1em; font-size: var(--text-sm); }
</style>
