/** One shared live connection (SSE) for the whole app, opened while at least one component uses it. */
import { computed, onBeforeUnmount, shallowRef, triggerRef } from 'vue'
import type { LiveRecent, LiveSnapshot } from '@/lib/types'

const WINDOW_S = 900
const snapshot = shallowRef<LiveSnapshot | null>(null)
const connected = shallowRef(false)
const enabled = shallowRef(true)
const total = shallowRef<{ t: number; w: number }[]>([])
const perDevice = shallowRef<Record<string, { t: number; w: number }[]>>({})
let users = 0
let es: EventSource | null = null
let seeded = false

async function seed() {
  if (seeded) return
  seeded = true
  try {
    const r = await fetch('/api/live/recent')
    if (r.status === 503) { enabled.value = false; return }
    const d = (await r.json()) as LiveRecent
    total.value = d.total.map(([t, w]) => ({ t, w }))
    perDevice.value = Object.fromEntries(Object.entries(d.devices).map(([id, a]) => [id, a.map(([t, w]) => ({ t, w }))]))
  } catch { /* the stream fills the window */ }
}

function onMessage(e: MessageEvent) {
  const s = JSON.parse(e.data) as LiveSnapshot
  snapshot.value = s
  const cut = s.at - WINDOW_S
  const arr = total.value
  if (!arr.length || s.at - arr[arr.length - 1]!.t > 0.5) arr.push({ t: s.at, w: s.total_w })
  while (arr.length && arr[0]!.t < cut) arr.shift()
  triggerRef(total)
  const pd = perDevice.value
  for (const [id, d] of Object.entries(s.devices)) {
    if (d.age > 5) continue
    const a = (pd[id] ||= [])
    if (!a.length || s.at - a[a.length - 1]!.t > 0.5) a.push({ t: s.at, w: d.w })
    while (a.length && a[0]!.t < cut) a.shift()
  }
  triggerRef(perDevice)
}

function open() {
  if (es) return
  void seed()
  es = new EventSource('/api/live/stream')
  es.onopen = () => { connected.value = true }
  es.onerror = () => { connected.value = false }
  es.onmessage = onMessage
}

function close() {
  es?.close()
  es = null
  connected.value = false
}

export function useLive() {
  users++
  open()
  onBeforeUnmount(() => { if (--users === 0) close() })
  const now = computed(() => snapshot.value?.at ?? Date.now() / 1000)
  return { snapshot, connected, enabled, total, perDevice, now }
}
