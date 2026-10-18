<script setup>
// Type part of a code or name; suggestions come from the WMS goods list.
import { ref, watch } from 'vue'
import { get } from '../api/client.js'

const model = defineModel({ type: String, default: '' })
defineProps({ label: String })
const options = ref([])
const id = `goods-${Math.random().toString(36).slice(2, 8)}`
let timer = null
watch(model, (q) => {
  clearTimeout(timer)
  timer = setTimeout(async () => { options.value = await get(`/api/v1/inventory/goods?q=${encodeURIComponent(q || '')}`).catch(() => []) }, 200)
}, { immediate: true })
</script>

<template>
  <label class="field">
    <span>{{ label }}</span>
    <input v-model="model" :list="id" autocomplete="off" required class="mono" />
    <datalist :id="id"><option v-for="o in options" :key="o.goods_code" :value="o.goods_code">{{ o.goods_desc }}</option></datalist>
  </label>
</template>
