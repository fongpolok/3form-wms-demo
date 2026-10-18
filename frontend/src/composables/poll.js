import { onBeforeUnmount, onMounted, ref } from 'vue'

// Load data now and every `everyMs`; keeps the last good data on errors.
export function usePolled(loader, everyMs = 10000) {
  const data = ref(null)
  const error = ref('')
  const loading = ref(true)
  let timer = null
  async function load() {
    try {
      data.value = await loader()
      error.value = ''
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }
  onMounted(() => { load(); if (everyMs) timer = setInterval(load, everyMs) })
  onBeforeUnmount(() => clearInterval(timer))
  return { data, error, loading, reload: load }
}
