// Browser storage that never throws (private windows / blocked storage just
// behave as empty). sessionStorage = this tab's login; localStorage = this
// tablet's device registration and preferences.
function wrap(getStore) {
  return {
    get(key) { try { return getStore().getItem(`tf.${key}`) } catch { return null } },
    set(key, value) { try { getStore().setItem(`tf.${key}`, value) } catch { /* ignore */ } },
    remove(key) { try { getStore().removeItem(`tf.${key}`) } catch { /* ignore */ } },
    getJSON(key, fallback) { try { return JSON.parse(this.get(key)) ?? fallback } catch { return fallback } },
    setJSON(key, value) { this.set(key, JSON.stringify(value)) },
  }
}
export const storage = { session: wrap(() => sessionStorage), local: wrap(() => localStorage) }
