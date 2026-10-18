<script setup>
import { useI18n } from 'vue-i18n'
import { get } from '../../api/client.js'
import { usePolled } from '../../composables/poll.js'
import PageHead from '../../components/PageHead.vue'

const { t } = useI18n()
const { data, error, loading } = usePolled(() => get('/stock/list/?max_page=200'), 30000)
</script>

<template>
  <PageHead :title="t('stock.title')" :subtitle="t('stock.subtitle')" />
  <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
  <p v-if="loading" class="muted">{{ t('common.loading') }}</p>
  <div v-if="data" class="card table-wrap">
    <p v-if="!data.results?.length" class="muted">{{ t('common.none') }}</p>
    <table v-else class="table">
      <thead><tr><th>{{ t('stock.code') }}</th><th>{{ t('stock.desc') }}</th><th>{{ t('stock.onhand') }}</th><th>Lot</th><th>Expiry</th></tr></thead>
      <tbody>
        <tr v-for="s in data.results" :key="s.id">
          <td class="mono">{{ s.goods_code }}</td><td>{{ s.goods_desc }}</td><td>{{ s.onhand_stock ?? s.goods_qty }}</td>
          <td class="mono">{{ s.lot_number }}</td><td>{{ s.expiry_date }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
