/** The device list shared by all views (one query), with name, room and colour lookups. */
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { api } from '@/lib/api'
import { slotVar } from '@/lib/colors'
import type { Device } from '@/lib/types'

export function useDevices() {
  const q = useQuery({ queryKey: ['devices'], queryFn: () => api.get<{ devices: Device[] }>('/api/devices'), staleTime: 30_000 })
  const list = computed(() => (q.data.value?.devices ?? []).filter((d) => !d.retired))
  const byId = computed(() => Object.fromEntries((q.data.value?.devices ?? []).map((d) => [d.id, d])))
  const slot = (id: string) => byId.value[id]?.slot ?? 0
  const color = (id: string) => slotVar(slot(id))
  return { q, list, byId, slot, color }
}
