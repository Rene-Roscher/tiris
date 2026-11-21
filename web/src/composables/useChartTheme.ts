import { computed } from 'vue'
import { useTheme } from './useTheme'
import { baseOption, slotColor, token } from '@/lib/charts'

/** Re-reads the design tokens whenever the theme changes; chart options depend on `theme.value`. */
export function useChartTheme() {
  const { isDark } = useTheme()
  const theme = computed(() => {
    void isDark.value
    return { base: baseOption(), slotColor, token, dark: isDark.value }
  })
  return theme
}
