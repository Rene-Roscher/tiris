/** The only place that knows the toast library. Views call notify.* only. */
import { markRaw } from 'vue'
import { toast } from 'vue-sonner'
import ToastCard from '@/components/ToastCard.vue'

type Tone = 'success' | 'error' | 'info'
function show(tone: Tone, title: string, description?: string) {
  return toast.custom(markRaw(ToastCard), { componentProps: { tone, title, description }, duration: tone === 'error' ? 8000 : 3500 })
}

export const notify = {
  success: (title: string, description?: string) => show('success', title, description),
  error: (title: string, description?: string) => show('error', title, description),
  info: (title: string, description?: string) => show('info', title, description),
}
