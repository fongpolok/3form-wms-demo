<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { get } from '../../api/client.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'

const { t } = useI18n()
const entityId = ref('')
const { data, error, reload } = usePolled(
  () => get(`/api/v1/audit?limit=300${entityId.value ? `&entity_id=${encodeURIComponent(entityId.value.trim())}` : ''}`), 0)
const show = (v) => (v == null ? '' : JSON.stringify(v))
</script>

<template>
  <PageHead :title="t('audit.title')" :subtitle="t('audit.subtitle')" />
  <form class="card row" @submit.prevent="reload">
    <label class="field grow"><span>ID</span><input v-model="entityId" class="mono" placeholder="WIP-B-… / WO-… / device id" /></label>
    <button class="btn btn-primary">{{ t('common.search') }}</button>
  </form>
  <p v-if="error" class="notice notice-error">{{ error }}</p>
  <div class="card table-wrap block">
    <table class="table">
      <thead><tr><th>{{ t('audit.when') }}</th><th>{{ t('audit.who') }}</th><th>{{ t('audit.what') }}</th><th>{{ t('audit.before') }}</th><th>{{ t('audit.after') }}</th><th>{{ t('common.reason') }}</th></tr></thead>
      <tbody>
        <tr v-for="a in data" :key="a.id">
          <td>{{ new Date(a.ts).toLocaleString() }}</td><td>{{ a.actor_name }} <span class="muted">({{ a.actor_role }})</span></td>
          <td><span class="mono">{{ a.action }}</span><br /><span class="muted mono">{{ a.entity_id }}</span></td>
          <td class="mono small">{{ show(a.before) }}</td><td class="mono small">{{ show(a.after) }}</td><td>{{ a.reason }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.grow { flex: 1; }
.row { align-items: flex-end; }
.block { margin-top: 20px; }
.small { font-size: 0.8125rem; max-width: 280px; word-break: break-word; }
</style>
