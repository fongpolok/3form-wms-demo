<script setup>
// Card around one chart: title, one-line subtitle, and a Chart / Table switch
// so every value is also available as text (accessibility + low-contrast relief).
import { ref } from 'vue'

defineProps({ title: String, subtitle: String })
const asTable = ref(false)
</script>

<template>
  <section class="card frame">
    <header class="row">
      <div class="grow">
        <h2>{{ title }}</h2>
        <p v-if="subtitle" class="muted sub">{{ subtitle }}</p>
      </div>
      <div class="seg" role="radiogroup" aria-label="View">
        <button type="button" role="radio" :aria-checked="!asTable" :class="{ on: !asTable }" @click="asTable = false">Chart</button>
        <button type="button" role="radio" :aria-checked="asTable" :class="{ on: asTable }" @click="asTable = true">Table</button>
      </div>
    </header>
    <div v-if="!asTable" class="plot"><slot /></div>
    <div v-else class="table-wrap"><slot name="table" /></div>
  </section>
</template>

<style scoped>
.frame { display: grid; gap: 16px; align-content: start; min-width: 0; }
.frame h2 { font-size: var(--text-lg); }
.sub { font-size: var(--text-sm); margin-top: 2px; }
.grow { flex: 1; min-width: 0; }
.plot { position: relative; min-width: 0; }
.seg { display: inline-flex; border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 2px; }
.seg button { min-height: 32px; padding: 0 10px; border: 0; border-radius: 8px; background: transparent; color: var(--ink-2);
              font: 600 0.875rem/1 var(--font-body); cursor: pointer; }
.seg button.on { background: var(--surface-2); color: var(--ink); box-shadow: 0 0 0 1px var(--line-strong); }
</style>
