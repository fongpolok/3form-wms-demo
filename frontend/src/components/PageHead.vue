<script setup>
defineProps({ title: String, subtitle: String })
</script>

<template>
  <header class="ph">
    <div>
      <h1>{{ title }}</h1>
      <p v-if="subtitle" class="muted">{{ subtitle }}</p>
    </div>
    <div class="ph-actions"><slot /></div>
  </header>
</template>

<style scoped>
.ph { display: flex; gap: 16px; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; margin-bottom: 24px; }
.ph p { margin-top: 6px; }
.ph-actions { display: flex; gap: 12px; flex-wrap: wrap; }
</style>
