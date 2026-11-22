<script setup lang="ts">
/*
  Sidebar on the canvas. Expanded: brand, live block (total + last minutes), search, navigation with a sliding
  marker, the devices drawing power with their share, and a footer with fetch status and quick buttons.
  Collapsed (rail): icons with tooltips; the live total stays visible as a small number.
*/
import { Activity, LayoutDashboard, Monitor, Moon, PanelLeftClose, PanelLeftOpen, Plug, Search, Settings, Sun, SunMoon, Wallet } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import { useResizeObserver } from '@vueuse/core'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import LiveSpark from '@/components/charts/LiveSpark.vue'
import LiveDot from '@/components/LiveDot.vue'
import Logo from '@/components/Logo.vue'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useDevices } from '@/composables/useDevices'
import { useLive } from '@/composables/useLive'
import { useTheme } from '@/composables/useTheme'
import { useTween } from '@/composables/useTween'
import { api } from '@/lib/api'
import { ago, watts } from '@/lib/format'
import { isMac, paletteOpen } from '@/lib/palette'
import type { Run } from '@/lib/types'

const props = withDefaults(defineProps<{ collapsed?: boolean; collapsible?: boolean }>(), { collapsed: false, collapsible: true })
const emit = defineEmits<{ navigate: []; toggle: [] }>()
const { t } = useI18n()
const route = useRoute()
const isActive = (to: string) => (to === '/' ? route.path === '/' : route.path.startsWith(to))
const { snapshot, connected, enabled, total: liveTotal } = useLive()
const { list: active, color } = useDevices()
const { mode } = useTheme()
const runs = useQuery({ queryKey: ['runs', 1], queryFn: () => api.get<Run[]>('/api/runs?limit=1'), refetchInterval: 60_000 })
const lastRun = computed(() => runs.data.value?.[0])
const runOk = computed(() => !lastRun.value?.status || lastRun.value.status === 'ok')

const items = computed(() => [
  { to: '/', label: t('nav.overview'), icon: LayoutDashboard },
  { to: '/live', label: t('nav.live'), icon: Activity },
  { to: '/devices', label: t('nav.devices'), icon: Plug, count: active.value.length || null },
  { to: '/costs', label: t('nav.costs'), icon: Wallet },
  { to: '/wall', label: t('nav.wall'), icon: Monitor },
])
const total = computed(() => snapshot.value?.total_w ?? null)
const totalTween = useTween(total)
const spark = computed(() => liveTotal.value.slice(-150))

// devices drawing power now (>= 0.5 W), with their share of the total
const drawing = computed(() => {
  const live = snapshot.value?.devices ?? {}, tot = total.value || 0
  return active.value
    .map((d) => ({ id: d.id, name: d.name, w: live[d.id]?.w ?? 0, on: d.status?.device_on !== false }))
    .filter((d) => d.on && d.w >= 0.5)
    .sort((a, b) => b.w - a.w)
    .map((d) => ({ ...d, share: tot > 0 ? d.w / tot : 0 }))
})
const shown = computed(() => drawing.value.slice(0, 6))

// the active surface slides between the main entries (a transition: a quick second click starts where it is)
const navBox = ref<HTMLElement | null>(null)
const marker = ref<{ y: number; h: number; x: number; w: number } | null>(null)
const markerReady = ref(false)
function place() {
  const el = navBox.value?.querySelector<HTMLElement>('a[data-main][aria-current="page"]')
  marker.value = el ? { y: el.offsetTop, h: el.offsetHeight, x: el.offsetLeft, w: el.offsetWidth } : null
}
onMounted(async () => { place(); await nextTick(); requestAnimationFrame(() => { markerReady.value = true }) })
watch(() => [route.path, props.collapsed], () => { markerReady.value = false; nextTick(() => { place(); requestAnimationFrame(() => { markerReady.value = true }) }) })
useResizeObserver(navBox, place)

const themeNext = computed(() => (mode.value === 'light' ? 'dark' : mode.value === 'dark' ? 'auto' : 'light'))
const themeIcon = computed(() => (mode.value === 'light' ? Sun : mode.value === 'dark' ? Moon : SunMoon))
const linkBase = 'group relative flex h-[30px] items-center rounded-md font-medium transition-[color,background-color]'
</script>

<template>
  <nav class="flex h-full flex-col gap-4 py-3" :class="collapsed ? 'items-center px-2' : 'pl-3 pr-2.5'" :aria-label="t('app.nav')">
    <!-- brand -->
    <div class="flex h-8 items-center gap-2" :class="collapsed ? 'justify-center' : 'px-2'">
      <Logo />
      <span v-if="!collapsed" class="text-base font-semibold tracking-tight">tiris</span>
    </div>

    <!-- live -->
    <RouterLink v-if="enabled && !collapsed" to="/live" @click="emit('navigate')"
                class="block rounded-lg border border-border bg-background px-3 pb-2 pt-2.5 shadow-xs transition-[border-color] hover:border-border-strong">
      <span class="flex items-center gap-2 text-xs text-caption">
        <LiveDot :on="connected" :beat="snapshot?.at" />{{ connected ? t('app.liveNow') : t('app.liveOff') }}
      </span>
      <span class="mt-1 block text-lg font-semibold tabular">{{ totalTween == null ? '–' : watts(totalTween) }}</span>
      <LiveSpark class="mt-1" :points="spark" :height="22" />
    </RouterLink>
    <Tooltip v-else-if="enabled">
      <TooltipTrigger as-child>
        <RouterLink to="/live" class="flex w-11 flex-col items-center gap-1 rounded-md py-1.5 text-xs font-medium tabular hover:bg-side-hover" @click="emit('navigate')">
          <LiveDot :on="connected" :beat="snapshot?.at" />{{ total == null ? '–' : Math.round(total) }}
        </RouterLink>
      </TooltipTrigger>
      <TooltipContent side="right">{{ t('app.liveNow') }}: {{ total == null ? '–' : watts(total) }}</TooltipContent>
    </Tooltip>

    <!-- search + navigation -->
    <div ref="navBox" class="relative flex flex-col gap-px" :class="collapsed ? 'items-center' : ''">
      <span v-if="marker" class="pointer-events-none absolute left-0 top-0 rounded-md bg-background shadow-[0_0_0_1px_var(--border),0_1px_2px_rgb(0_0_0/0.06)]" aria-hidden="true"
            :class="markerReady ? 'transition-[translate] duration-(--ease-settle-ms) ease-settle' : ''"
            :style="{ translate: `${marker.x}px ${marker.y}px`, height: `${marker.h}px`, width: `${marker.w}px` }" />
      <Tooltip :disabled="!collapsed">
        <TooltipTrigger as-child>
          <button type="button" class="mb-2 flex h-8 items-center gap-2.5 rounded-md border border-border bg-background text-sm text-caption shadow-xs transition-[color,border-color] hover:border-border-strong hover:text-foreground"
                  :class="collapsed ? 'w-9 justify-center' : 'px-2'" :aria-label="t('palette.title')" @click="paletteOpen = true; emit('navigate')">
            <Search class="size-4" aria-hidden="true" />
            <template v-if="!collapsed">{{ t('palette.search') }}<span class="flex-1" aria-hidden="true" />
              <kbd class="rounded-sm border border-border px-1 text-xs">{{ isMac ? '⌘' : t('palette.ctrl') }} K</kbd></template>
          </button>
        </TooltipTrigger>
        <TooltipContent side="right">{{ t('palette.title') }} · {{ isMac ? '⌘' : t('palette.ctrl') }} K</TooltipContent>
      </Tooltip>
      <Tooltip v-for="i in items" :key="i.to" :disabled="!collapsed">
        <TooltipTrigger as-child>
          <RouterLink :to="i.to" :aria-current="isActive(i.to) ? 'page' : undefined" data-main :aria-label="collapsed ? i.label : undefined"
                      :class="[linkBase, collapsed ? 'w-9 justify-center' : 'gap-2.5 px-2', isActive(i.to) ? 'text-foreground' : 'text-muted-foreground hover:bg-side-hover hover:text-foreground']"
                      @click="emit('navigate')">
            <component :is="i.icon" class="size-4" :class="isActive(i.to) ? 'text-foreground' : 'text-caption group-hover:text-foreground'" aria-hidden="true" />
            <template v-if="!collapsed">{{ i.label }}<span class="flex-1" aria-hidden="true" />
              <span v-if="i.count" class="text-xs font-normal text-caption tabular">{{ i.count }}</span></template>
          </RouterLink>
        </TooltipTrigger>
        <TooltipContent side="right">{{ i.label }}</TooltipContent>
      </Tooltip>
    </div>

    <!-- drawing now -->
    <section v-if="enabled && !collapsed" aria-labelledby="side-drawing" class="min-h-0">
      <h2 id="side-drawing" class="flex h-6 items-center px-2 text-xs font-medium text-caption">
        {{ t('app.drawing') }}<span class="flex-1" aria-hidden="true" /><span class="tabular">{{ drawing.length }}/{{ active.length }}</span>
      </h2>
      <ul class="flex flex-col gap-px text-sm">
        <li v-for="d in shown" :key="d.id">
          <RouterLink :to="`/devices/${d.id}`" @click="emit('navigate')"
                      class="block rounded-md px-2 py-1.5 text-muted-foreground transition-[color,background-color] hover:bg-side-hover hover:text-foreground">
            <span class="flex items-center gap-2">
              <span class="truncate" :title="d.name">{{ d.name }}</span><span class="flex-1" aria-hidden="true" />
              <span class="text-xs font-medium text-foreground tabular">{{ watts(d.w) }}</span>
            </span>
            <span class="mt-1 block h-1 overflow-hidden rounded-full bg-border" aria-hidden="true">
              <span class="block h-full origin-left rounded-full transition-transform duration-(--ease-settle-ms) ease-settle"
                    :style="{ background: color(d.id), transform: `scaleX(${Math.max(0.02, d.share).toFixed(3)})` }" />
            </span>
          </RouterLink>
        </li>
        <li v-if="!drawing.length" class="px-2 py-1.5 text-xs text-caption">{{ t('app.nothingDrawing') }}</li>
        <li v-if="drawing.length > shown.length" class="px-2 py-1 text-xs text-caption">{{ t('app.moreDrawing', { n: drawing.length - shown.length }) }}</li>
      </ul>
    </section>

    <div class="flex-1" aria-hidden="true" />

    <!-- footer -->
    <div class="flex flex-col gap-2" :class="collapsed ? 'items-center' : ''">
      <RouterLink v-if="lastRun && !collapsed" to="/settings" class="flex items-center gap-2 rounded-md px-2 text-xs hover:text-foreground" :class="runOk ? 'text-caption' : 'text-warn'" @click="emit('navigate')">
        <span class="size-1.5 shrink-0 rounded-full" :class="runOk ? 'bg-good-fill' : 'bg-warn-fill'" aria-hidden="true" />
        <span class="truncate">{{ runOk ? t('app.lastRun', { when: ago(lastRun.finished_at ?? lastRun.started_at) }) : t('app.runFailed') }}</span>
      </RouterLink>
      <div class="flex gap-0.5" :class="collapsed ? 'flex-col' : 'items-center'">
        <Tooltip>
          <TooltipTrigger as-child>
            <RouterLink to="/settings" :aria-label="t('nav.settings')" :aria-current="isActive('/settings') ? 'page' : undefined" @click="emit('navigate')"
                        class="grid size-8 place-items-center rounded-md transition-[color,background-color] hover:bg-side-hover hover:text-foreground"
                        :class="isActive('/settings') ? 'bg-background text-foreground shadow-[0_0_0_1px_var(--border)]' : 'text-caption'">
              <Settings class="size-4" aria-hidden="true" />
            </RouterLink>
          </TooltipTrigger>
          <TooltipContent :side="collapsed ? 'right' : 'top'">{{ t('nav.settings') }}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger as-child>
            <button type="button" class="grid size-8 place-items-center rounded-md text-caption transition-[color,background-color] hover:bg-side-hover hover:text-foreground"
                    :aria-label="`${t('app.theme')}: ${t(`app.themes.${mode}`)}`" @click="mode = themeNext">
              <component :is="themeIcon" class="size-4" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent :side="collapsed ? 'right' : 'top'">{{ t('app.theme') }}: {{ t(`app.themes.${mode}`) }}</TooltipContent>
        </Tooltip>
        <span v-if="!collapsed" class="flex-1" aria-hidden="true" />
        <Tooltip v-if="collapsible">
          <TooltipTrigger as-child>
            <button type="button" class="grid size-8 place-items-center rounded-md text-caption transition-[color,background-color] hover:bg-side-hover hover:text-foreground"
                    :aria-label="collapsed ? t('app.expand') : t('app.collapse')" :aria-expanded="!collapsed" @click="emit('toggle')">
              <PanelLeftOpen v-if="collapsed" class="size-4" aria-hidden="true" /><PanelLeftClose v-else class="size-4" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent :side="collapsed ? 'right' : 'top'">{{ collapsed ? t('app.expand') : t('app.collapse') }} · [</TooltipContent>
        </Tooltip>
      </div>
    </div>
  </nav>
</template>
