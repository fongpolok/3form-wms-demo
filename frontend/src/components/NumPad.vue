<script setup>
// Large on-screen keypad for gloved hands. v-model holds a string of digits.
const model = defineModel({ type: String, default: '' })
const props = defineProps({ maxLength: { type: Number, default: 8 }, decimal: { type: Boolean, default: false } })
const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9']

function press(k) {
  if (model.value.length >= props.maxLength) return
  if (k === '.' && model.value.includes('.')) return
  model.value += k
}
</script>

<template>
  <div class="pad" role="group" aria-label="Number keypad">
    <button v-for="k in keys" :key="k" type="button" class="key" @click="press(k)">{{ k }}</button>
    <button type="button" class="key" @click="decimal ? press('.') : (model = '')" :aria-label="decimal ? 'Decimal point' : 'Clear'">
      {{ decimal ? '.' : 'C' }}
    </button>
    <button type="button" class="key" @click="press('0')">0</button>
    <button type="button" class="key" @click="model = model.slice(0, -1)" aria-label="Delete last digit">⌫</button>
  </div>
</template>

<style scoped>
.pad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.key { min-height: 72px; border-radius: 14px; border: 1px solid var(--line-strong); background: var(--surface);
       color: var(--ink); font: 650 1.75rem/1 var(--font-body); cursor: pointer; }
.key:active { background: var(--accent-soft); }
</style>
