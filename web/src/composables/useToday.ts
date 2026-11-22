/** Today's local date (YYYY-MM-DD) that changes at midnight, so views left open for days roll over on their own. */
import { useIntervalFn, useNow } from '@vueuse/core'
import { computed } from 'vue'

export function useToday() {
  const now = useNow({ scheduler: (cb) => useIntervalFn(cb, 30_000) })
  return computed(() => now.value.toLocaleDateString('sv-SE'))
}
