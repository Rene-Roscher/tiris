/** The only place that knows the toast library. Views call notify.* only. */
import { markRaw, reactive } from 'vue'
import { toast } from 'vue-sonner'
import PillToast from '@/components/PillToast.vue'

export type PillType = 'success' | 'error' | 'warning' | 'info' | 'loading'
export interface PillOptions {
  type?: PillType
  title: string
  description?: string
  /** ms; default 4 s, errors 6 s, with an action 8 s; loading stays until updated */
  duration?: number
  action?: { label: string; onClick: () => void }
  /** 0 to 1, shows a progress line */
  progress?: number
}
export interface PillState extends Required<Pick<PillOptions, 'type' | 'title'>>, Omit<PillOptions, 'type' | 'title'> {
  id: string
  count: number
  lifeRev: number
  end?: () => void
}
export interface PillHandle { update: (patch: Partial<PillOptions>) => void; dismiss: () => void }

let seq = 0
const RESTART: (keyof PillOptions)[] = ['type', 'title', 'description', 'duration', 'action']
const live = new Set<PillState>()
const handles = new WeakMap<PillState, PillHandle>()
// the same message again counts up on the open pill instead of stacking a copy
const same = (st: PillState, o: PillOptions) =>
  st.type === (o.type ?? 'info') && st.title === o.title && (st.description ?? '') === (o.description ?? '') &&
  st.type !== 'loading' && !st.action && !o.action && st.progress == null && o.progress == null

export function show(o: PillOptions): PillHandle {
  for (const st of live) {
    if (same(st, o)) {
      st.count++
      st.lifeRev++
      return handles.get(st)!
    }
  }
  const state = reactive<PillState>({ id: `t-${++seq}`, count: 1, lifeRev: 0, ...o, type: o.type ?? 'info' }) as PillState
  let gone = false
  const end = () => {
    gone = true
    live.delete(state)
  }
  state.end = end
  const handle: PillHandle = markRaw({
    update(patch) {
      if (gone) return
      const restart = RESTART.some((k) => k in patch)
      Object.assign(state, patch)
      if (restart) state.lifeRev++
    },
    dismiss: () => toast.dismiss(state.id),
  })
  handles.set(state, handle)
  live.add(state)
  toast.custom(markRaw(PillToast), {
    id: state.id,
    duration: Infinity, // the pill keeps its own time (pauses on hover, only the front one runs)
    unstyled: true,
    dismissible: false, // Sonner's swipe knows one axis; the pill drags itself
    componentProps: { state },
    onDismiss: end,
    onAutoClose: end,
  })
  return handle
}

export const notify = {
  success: (title: string, description?: string) => show({ type: 'success', title, description }),
  error: (title: string, description?: string) => show({ type: 'error', title, description }),
  warning: (title: string, description?: string) => show({ type: 'warning', title, description }),
  info: (title: string, description?: string) => show({ type: 'info', title, description }),
  loading: (title: string, description?: string) => show({ type: 'loading', title, description }),
}

export const dismissAll = () => toast.dismiss()
