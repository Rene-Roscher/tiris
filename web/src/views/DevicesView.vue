<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import DeviceCard from '@/components/devices/DeviceCard.vue'
import Segmented from '@/components/Segmented.vue'
import StateMessage from '@/components/StateMessage.vue'
import { Button } from '@/components/ui/button'
import { useAction } from '@/composables/useAction'
import { useLive } from '@/composables/useLive'
import { ApiError, api } from '@/lib/api'
import type { Device } from '@/lib/types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const live = useLive()
const q = useQuery({
  queryKey: ['devices'],
  queryFn: () => api.get<{ devices: Device[] }>('/api/devices'),
  refetchInterval: (query) => (query.state.data?.devices.some((d) => d.firmware?.pending) ? 8_000 : 30_000),
})
const all = computed(() => q.data.value?.devices ?? [])
const room = computed(() => (typeof route.query.room === 'string' ? route.query.room : 'all'))
const active = computed(() => all.value.filter((d) => !d.retired && (room.value === 'all' || (d.room ?? '') === (room.value === '-' ? '' : room.value))))
const retired = computed(() => all.value.filter((d) => d.retired))
const rooms = computed(() => [...new Set(all.value.map((d) => d.room).filter((x): x is string => !!x))].sort())
const categories = computed(() => [...new Set(all.value.map((d) => d.category).filter((x): x is string => !!x))].sort())
const groups = computed(() => {
  const g = new Map<string, Device[]>()
  for (const d of active.value) {
    const k = d.room || ''
    g.set(k, [...(g.get(k) ?? []), d])
  }
  return [...g.entries()].sort((a, b) => (a[0] === '' ? 1 : b[0] === '' ? -1 : a[0].localeCompare(b[0])))
})
const stats = computed(() => {
  const a = all.value.filter((d) => !d.retired)
  return [
    { n: a.length, label: t('devices.summary.plugs') },
    { n: a.filter((d) => d.status.device_on).length, label: t('devices.summary.on') },
    { n: a.filter((d) => d.status.reachable && !d.status.device_on).length, label: t('devices.summary.off') },
    { n: a.filter((d) => !d.status.reachable).length, label: t('devices.summary.unreachable'), warn: true },
    { n: a.filter((d) => d.firmware?.available).length, label: t('devices.summary.updates'), warn: true },
  ]
})
const { busy, run } = useAction([['devices']], () => t('devices.title'))
const restore = (d: Device) => run(() => api.patch(`/api/devices/${d.id}`, { retired: false }))
const roomOptions = computed(() => [{ value: 'all', label: t('common.all') }, ...rooms.value.map((r) => ({ value: r, label: r })), { value: '-', label: t('devices.noRoom') }])
const setRoom = (v: string) => router.replace({ query: { ...route.query, room: v === 'all' ? undefined : v } })
const noTapo = computed(() => q.error.value instanceof ApiError && q.error.value.status === 503)
</script>

<template>
  <div class="mb-7 flex min-h-9 flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1">
      <h1 class="font-semibold">{{ t('devices.title') }}</h1>
      <p v-if="all.length" class="text-sm text-caption tabular">
        <template v-for="(s, i) in stats" :key="s.label"><template v-if="!s.warn || s.n">{{ i ? ' · ' : '' }}<span :class="s.warn && s.n ? 'font-medium text-warn' : ''">{{ s.n }} {{ s.label }}</span></template></template>
      </p>
    </div>
    <Segmented v-if="rooms.length" :model-value="room" :options="roomOptions" :label="t('devices.room')" @update:model-value="(v) => setRoom(String(v))" />
  </div>

  <StateMessage v-if="noTapo" kind="setup" :title="t('states.noTapoTitle')" :body="t('states.noTapoBody')" />
  <StateMessage v-else-if="q.isError.value" kind="error" :title="t('states.errorTitle')"
                :body="t('states.errorBody', { detail: q.error.value?.message ?? '' })" :action="t('common.retry')" @action="q.refetch()" />
  <div v-else-if="q.isLoading.value" class="flex flex-col gap-2">
    <div v-for="i in 5" :key="i" class="h-14 animate-pulse rounded-md bg-muted" />
  </div>
  <StateMessage v-else-if="!all.length" :title="t('states.noDataTitle')" :body="t('states.noDataBody')" />

  <div v-else class="flex flex-col gap-8">
    <section v-for="[r, devs] in groups" :key="r">
      <h2 class="mb-1 flex items-baseline gap-2 text-xs font-medium text-caption">
        {{ r || t('devices.noRoom') }}<span class="tabular">{{ devs.length }}</span>
      </h2>
      <ul class="divide-y divide-border border-y border-border">
        <DeviceCard v-for="d in devs" :key="d.id" :device="d" :live-w="live.snapshot.value?.devices[d.id]?.w" :rooms="rooms" :categories="categories" />
      </ul>
    </section>

    <details v-if="retired.length" class="text-sm">
      <summary class="cursor-pointer text-caption hover:text-foreground">{{ t('devices.archivedCount', { n: retired.length }) }}</summary>
      <ul class="mt-2 divide-y divide-border border-y border-border">
        <li v-for="d in retired" :key="d.id" class="flex items-center justify-between gap-3 py-2.5">
          <span>{{ d.name }} <span class="text-caption">{{ d.model }}, {{ d.ip }}</span></span>
          <Button type="button" variant="outline" size="sm" :disabled="busy" @click="restore(d)">{{ t('devices.maintenance.restore') }}</Button>
        </li>
      </ul>
    </details>
  </div>
</template>
