/** A number that glides to each new value (ease-out, default 350 ms) instead of jumping. Interruptible: a new
    value starts from the number on screen. Reduced motion: the value is shown as is. */
import { onBeforeUnmount, type Ref, ref, watch } from 'vue'

export function useTween(source: Ref<number | null | undefined>, ms = 350) {
  const out = ref<number | null>(source.value ?? null)
  const reduce = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
  let raf = 0
  watch(source, (to) => {
    cancelAnimationFrame(raf)
    if (to == null || out.value == null || reduce || document.hidden) { out.value = to ?? null; return }
    const from = out.value, t0 = performance.now()
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / ms), e = 1 - (1 - p) ** 3
      out.value = from + (to - from) * e
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  })
  onBeforeUnmount(() => cancelAnimationFrame(raf))
  return out
}
