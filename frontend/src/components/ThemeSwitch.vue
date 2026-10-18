<script setup>
import { useI18n } from 'vue-i18n'
import { applyTheme, theme, THEMES } from '../composables/theme.js'

const { t } = useI18n()
</script>

<template>
  <div class="seg" role="radiogroup" :aria-label="t('theme.label')">
    <button v-for="th in THEMES" :key="th" type="button" role="radio" :aria-checked="theme === th"
            :class="{ on: theme === th }" @click="applyTheme(th)">{{ t(`theme.${th}`) }}</button>
  </div>
</template>

<style scoped>
.seg { display: inline-flex; border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 2px; background: var(--surface-2); }
.seg button { min-height: 36px; padding: 0 12px; border: 0; border-radius: 8px; background: transparent; color: var(--ink-2);
              font: 600 var(--text-sm)/1 var(--font-body); cursor: pointer; }
.seg button.on { background: var(--surface); color: var(--ink); box-shadow: 0 0 0 1px var(--line-strong); }
</style>
