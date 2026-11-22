<script setup lang="ts">
/** Sidebar on the canvas: brand with live total, navigation, the devices drawing power right now, settings. */
import { Activity, LayoutDashboard, Plug, Search, Settings, Wallet } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import Logo from '@/components/Logo.vue'
import { useLive } from '@/composables/useLive'
import { api } from '@/lib/api'
import { slotVar } from '@/lib/colors'
import { isMac, paletteOpen } from '@/lib/palette'
import { ago, watts } from '@/lib/format'
import type { Device, Run } from '@/lib/types'

defineEmits<{ navigate: [] }>()
const { t } = useI18n()
const route = useRoute()
const isActive = (to: string) => (to === '/' ? route.path === '/' : route.path.startsWith(to))
const { snapshot, connected, enabled } = useLive()
const runs = useQuery({ queryKey: ['runs', 1], queryFn: () => api.get<Run[]>('/api/runs?limit=1'), refetchInterval: 60_000 })
const devs = useQuery({ queryKey: ['devices'], queryFn: () => api.get<{ devices: Device[] }>('/api/devices'), staleTime: 30_000 })
const lastRun = computed(() => runs.data.value?.[0])
const active = computed(() => (devs.data.value?.devices ?? []).filter((d) => !d.retired))
const items = computed(() => [
  { to: '/', label: t('nav.overview'), icon: LayoutDashboard },
  { to: '/live', label: t('nav.live'), icon: Activity },
  { to: '/devices', label: t('nav.devices'), icon: Plug, count: active.value.length || null },
  { to: '/costs', label: t('nav.costs'), icon: Wallet },
])
const total = computed(() => snapshot.value?.total_w ?? null)
// the five devices drawing the most right now
const drawing = computed(() => {
  const live = snapshot.value?.devices ?? {}
  return active.value
    .map((d) => ({ id: d.id, name: d.name, slot: d.slot, on: d.status?.device_on !== false, w: live[d.id]?.w ?? null }))
    .sort((a, b) => Number(b.on) - Number(a.on) || (b.w ?? -1) - (a.w ?? -1))
    .slice(0, 5)
})
const navClass = (on: boolean) => on
  ? 'bg-background text-foreground shadow-[0_0_0_1px_var(--border),0_1px_2px_rgb(0_0_0/0.06)]'
  : 'text-muted-foreground hover:bg-side-hover hover:text-foreground'
</script>

<template>
  <nav class="flex h-full flex-col gap-5 py-3 pl-3 pr-2.5" :aria-label="t('app.nav')">
    <div class="flex h-8 items-center gap-2 px-2">
      <Logo />
      <span class="text-base font-semibold tracking-tight">tiris</span>
      <span class="flex-1" aria-hidden="true" />
      <span v-if="enabled" class="inline-flex h-[22px] items-center gap-1.5 rounded-full bg-side-hover px-2 text-xs font-medium text-muted-foreground"
            :title="connected ? t('app.liveOn') : t('app.liveOff')">
        <span class="size-1.5 rounded-full" :class="connected ? 'bg-good-fill' : 'bg-caption'" aria-hidden="true" />
        <span class="tabular text-foreground">{{ total == null ? '–' : watts(total) }}</span>
      </span>
    </div>

    <div class="flex flex-col gap-px">
      <button type="button" class="mb-2 flex h-8 items-center gap-2.5 rounded-md border border-border bg-background px-2 text-sm text-caption shadow-xs transition-[color,border-color] hover:border-border-strong hover:text-foreground"
              @click="paletteOpen = true; $emit('navigate')">
        <Search class="size-4" aria-hidden="true" />{{ t('palette.search') }}
        <span class="flex-1" aria-hidden="true" />
        <kbd class="rounded-sm border border-border px-1 text-xs">{{ isMac ? '⌘' : t('palette.ctrl') }} K</kbd>
      </button>
      <RouterLink
        v-for="i in items" :key="i.to" :to="i.to" @click="$emit('navigate')"
        :aria-current="isActive(i.to) ? 'page' : undefined"
        class="group flex h-[30px] items-center gap-2.5 rounded-md px-2 font-medium transition-[color,background-color,box-shadow]"
        :class="navClass(isActive(i.to))"
      >
        <component :is="i.icon" class="size-4" :class="isActive(i.to) ? 'text-foreground' : 'text-caption group-hover:text-foreground'" aria-hidden="true" />
        {{ i.label }}
        <span class="flex-1" aria-hidden="true" />
        <span v-if="i.count" class="text-xs font-normal text-caption tabular">{{ i.count }}</span>
      </RouterLink>
    </div>

    <section v-if="enabled && drawing.length" :aria-labelledby="'side-drawing'">
      <h2 id="side-drawing" class="flex h-6 items-center px-2 text-xs font-medium text-caption">{{ t('app.drawing') }}</h2>
      <ul class="flex flex-col gap-px text-sm">
        <li v-for="d in drawing" :key="d.id">
          <RouterLink :to="`/devices/${d.id}`" @click="$emit('navigate')"
                      class="grid h-7 grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-2.5 rounded-md px-2 text-muted-foreground transition-[color,background-color] hover:bg-side-hover hover:text-foreground">
            <span class="size-2 rounded-sm" :style="{ background: slotVar(d.slot) }" aria-hidden="true" />
            <span class="truncate" :title="d.name">{{ d.name }}</span>
            <span class="text-xs tabular" :class="d.on && (d.w ?? 0) >= 0.5 ? 'font-medium text-foreground' : 'text-caption'">
              {{ !d.on ? t('app.off') : d.w == null ? '–' : watts(d.w) }}
            </span>
          </RouterLink>
        </li>
        <li>
          <RouterLink to="/devices" @click="$emit('navigate')"
                      class="flex h-7 items-center rounded-md px-2 text-xs text-caption transition-[color,background-color] hover:bg-side-hover hover:text-foreground">
            {{ t('app.allDevices', { n: active.length }) }}
          </RouterLink>
        </li>
      </ul>
    </section>

    <div class="flex-1" aria-hidden="true" />
    <div class="flex flex-col gap-1">
      <RouterLink to="/settings" @click="$emit('navigate')" :aria-current="isActive('/settings') ? 'page' : undefined"
                  class="group flex h-[30px] items-center gap-2.5 rounded-md px-2 font-medium transition-[color,background-color,box-shadow]"
                  :class="navClass(isActive('/settings'))">
        <Settings class="size-4" :class="isActive('/settings') ? 'text-foreground' : 'text-caption group-hover:text-foreground'" aria-hidden="true" />
        {{ t('nav.settings') }}
      </RouterLink>
      <p v-if="lastRun" class="truncate px-2 pt-1 text-xs" :class="lastRun.status && lastRun.status !== 'ok' ? 'text-warn' : 'text-caption'">
        {{ lastRun.status && lastRun.status !== 'ok' ? t('app.runFailed') : t('app.lastRun', { when: ago(lastRun.finished_at ?? lastRun.started_at) }) }}
      </p>
    </div>
  </nav>
</template>
