/** Open state of the command palette, shared by the sidebar button, the mobile header and the shortcut. */
import { ref } from 'vue'

export const paletteOpen = ref(false)
export const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
