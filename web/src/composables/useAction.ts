/** Runs a write against the API with one in-flight guard, a toast on success or error, and query invalidation. */
import { useQueryClient } from '@tanstack/vue-query'
import { ref } from 'vue'
import { notify } from '@/lib/toast'

export function useAction(invalidate: unknown[][], errorTitle: () => string) {
  const qc = useQueryClient()
  const busy = ref(false)
  async function run<T>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> {
    if (busy.value) return undefined
    busy.value = true
    try {
      const r = await fn()
      if (ok) notify.success(ok)
      await Promise.all(invalidate.map((k) => qc.invalidateQueries({ queryKey: k })))
      return r
    } catch (e) {
      notify.error(errorTitle(), (e as Error).message)
      return undefined
    } finally {
      busy.value = false
    }
  }
  return { busy, run }
}
