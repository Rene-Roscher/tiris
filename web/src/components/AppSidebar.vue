<script setup lang="ts">
import { Activity, LayoutDashboard, Plug, Settings, Wallet } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import Logo from '@/components/Logo.vue'
import { useLive } from '@/composables/useLive'
import { api } from '@/lib/api'
import { ago } from '@/lib/format'
import type { Run } from '@/lib/types'

defineEmits<{ navigate: [] }>()
const { t } = useI18n()
const route = useRoute()
const isActive = (to: string) => (to === '/' ? route.path === '/' : route.path.startsWith(to))
const { connected, enabled } = useLive()
const runs = useQuery({ queryKey: ['runs', 1], queryFn: () => api.get<Run[]>('/api/runs?limit=1'), refetchInterval: 60_000 })
const lastRun = computed(() => runs.data.value?.[0])
const items = computed(() => [
  { to: '/', label: t('nav.overview'), icon: LayoutDashboard },
  { to: '/live', label: t('nav.live'), icon: Activity },
  { to: '/devices', label: t('nav.devices'), icon: Plug },
  { to: '/costs', label: t('nav.costs'), icon: Wallet },
  { to: '/settings', label: t('nav.settings'), icon: Settings },
])
</script>

<template>
  <nav class="flex h-full flex-col gap-1 px-3 py-4" :aria-label="t('app.openMenu')">
    <div class="mb-4 flex items-center gap-2 px-2">
      <Logo />
      <span class="text-md font-semibold tracking-tight">tiris</span>
    </div>
    <RouterLink
      v-for="i in items" :key="i.to" :to="i.to" @click="$emit('navigate')"
      :aria-current="isActive(i.to) ? 'page' : undefined"
      class="flex h-8 items-center gap-2.5 rounded-md px-2 transition-[color,background-color] duration-150"
      :class="isActive(i.to) ? 'bg-active font-medium text-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
    >
      <component :is="i.icon" class="size-4" aria-hidden="true" />
      {{ i.label }}
    </RouterLink>
    <div class="flex-1" aria-hidden="true" />
    <div class="flex flex-col gap-1.5 px-2 text-sm text-caption">
      <p v-if="enabled" class="flex items-center gap-2">
        <span class="size-1.5 rounded-full" :class="connected ? 'bg-good-fill' : 'bg-caption'" aria-hidden="true" />
        {{ connected ? t('app.liveOn') : t('app.liveOff') }}
      </p>
      <p v-if="lastRun" class="truncate" :class="lastRun.status && lastRun.status !== 'ok' ? 'text-warn' : ''">
        {{ lastRun.status && lastRun.status !== 'ok' ? t('app.runFailed') : t('app.lastRun', { when: ago(lastRun.finished_at ?? lastRun.started_at) }) }}
      </p>
    </div>
  </nav>
</template>
