import { useColorMode } from '@vueuse/core'
import { computed } from 'vue'

/** light | dark | auto, stored in localStorage; `.dark` on <html>. */
export function useTheme() {
  const mode = useColorMode({ attribute: 'class', modes: { light: '', dark: 'dark' }, storageKey: 'tiris.theme', emitAuto: true })
  const isDark = computed(() => mode.state.value === 'dark')
  return { mode: mode.store, isDark }
}
