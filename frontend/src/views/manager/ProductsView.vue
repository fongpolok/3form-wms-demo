<script setup>
// Products & recipes (PIC and Engineering Manager; every save is audited).
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get, post } from '../../api/client.js'
import { pick } from '../../i18n/index.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'
import GoodsPicker from '../../components/GoodsPicker.vue'

const { t } = useI18n()
const { data, reload, error } = usePolled(() => get('/api/v1/inventory/products'), 0)
const editing = ref(null)
const msg = ref({ text: '', kind: 'ok' })
const steps = computed(() => data.value?.steps || [])

function edit(p) {
  editing.value = p ? JSON.parse(JSON.stringify(p)) : { goods_code: '', name: '', shelf_life_days: 730, routing: [], recipe: [] }
  if (!editing.value.routing.length) editing.value.routing = steps.value.map((s) => s.code)
  msg.value = { text: '' }
}
function toggleStep(code) {
  const r = editing.value.routing
  editing.value.routing = r.includes(code) ? r.filter((c) => c !== code) : steps.value.map((s) => s.code).filter((c) => r.includes(c) || c === code)
}
async function save() {
  try {
    const body = { ...editing.value, routing: editing.value.routing.length === steps.value.length ? [] : editing.value.routing }
    await post('/api/v1/inventory/products', body)
    msg.value = { kind: 'ok', text: `${editing.value.goods_code} ✓` }
    editing.value = null; reload()
  } catch (e) { msg.value = { kind: 'error', text: e.message } }
}
</script>

<template>
  <PageHead :title="t('nav.products')" :subtitle="t('products.subtitle')">
    <button class="btn btn-primary" @click="edit(null)">{{ t('products.add') }}</button>
  </PageHead>
  <p v-if="msg.text" :class="['notice', msg.kind === 'ok' ? 'notice-ok' : 'notice-error']" role="status">{{ msg.text }}</p>
  <p v-if="error" class="notice notice-error">{{ error }}</p>

  <section v-if="editing" class="card stack editor" aria-label="Product editor">
    <div class="form">
      <GoodsPicker v-model="editing.goods_code" :label="t('wo.product')" />
      <label class="field"><span>{{ t('wo.productName') }}</span><input v-model="editing.name" /></label>
      <label class="field"><span>{{ t('products.shelfLife') }}</span><input v-model.number="editing.shelf_life_days" type="number" min="1" /></label>
    </div>
    <fieldset class="steps"><legend>{{ t('products.steps') }}</legend>
      <label v-for="s in steps" :key="s.code" class="chk"><input type="checkbox" :checked="editing.routing.includes(s.code)"
             :disabled="s.is_qc" @change="toggleStep(s.code)" /> {{ pick(s.name) }}</label>
    </fieldset>
    <div>
      <h3>{{ t('products.recipe') }}</h3>
      <div v-for="(line, i) in editing.recipe" :key="i" class="row line">
        <GoodsPicker v-model="line.material_code" :label="t('products.material')" />
        <label class="field"><span>{{ t('products.perPiece') }}</span><input v-model.number="line.qty_per_piece" type="number" min="0" step="any" /></label>
        <button type="button" class="btn btn-quiet" @click="editing.recipe.splice(i, 1)" :aria-label="t('products.remove')">✕</button>
      </div>
      <button type="button" class="btn" @click="editing.recipe.push({ material_code: '', qty_per_piece: 1 })">{{ t('products.addLine') }}</button>
    </div>
    <div class="row"><button class="btn btn-primary" @click="save">{{ t('common.save') }}</button><button class="btn" @click="editing = null">{{ t('common.cancel') }}</button></div>
  </section>

  <div class="grid">
    <article v-for="p in data?.products || []" :key="p.goods_code" class="card stack">
      <div class="row"><div class="grow"><strong class="mono">{{ p.goods_code }}</strong><p>{{ p.name }}</p></div>
        <button class="btn" @click="edit(p)">{{ t('common.edit') }}</button></div>
      <p class="muted">{{ t('products.shelfLife') }}: {{ p.shelf_life_days }} · {{ p.routing.length ? p.routing.join(' → ') : t('products.allSteps') }}</p>
      <ul><li v-for="r in p.recipe" :key="r.material_code"><span class="mono">{{ r.material_code }}</span> × {{ r.qty_per_piece }}</li></ul>
    </article>
  </div>
</template>

<style scoped>
.editor { margin-bottom: 20px; border-color: var(--accent); }
.form { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.steps { border: 1px solid var(--line); border-radius: var(--radius); padding: 12px 16px; display: flex; flex-wrap: wrap; gap: 16px; }
.chk { display: flex; gap: 6px; align-items: center; }
.chk input { width: auto; min-height: auto; }
.line { align-items: flex-end; margin-bottom: 8px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.grow { flex: 1; }
ul { margin: 0; padding-left: 1.1em; font-size: var(--text-sm); }
h3 { font-size: var(--text); margin-bottom: 8px; }
</style>
