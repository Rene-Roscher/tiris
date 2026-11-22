<script setup lang="ts">
/*
  Wall view: a tablet or screen that stays on. Big numbers readable from across the room, no shell, controls that
  hide after a few seconds without input. Made to run for weeks:
  - keeps the screen on (Screen Wake Lock, taken again when the tab comes back),
  - moves the whole content by up to 2 px every minute (no burn-in on OLED),
  - reloads itself once a night at 04:00 (fresh build, fresh memory),
  - every number comes from data that refreshes itself (live stream, queries with intervals).
*/
import { ArrowLeft, Maximize, Minimize, Sun } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import { useFullscreen, useIdle, useIntervalFn, useNow, useWakeLock } from '@vueuse/core'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import LiveSpark from '@/components/charts/LiveSpark.vue'
import LiveDot from '@/components/LiveDot.vue'
import Logo from '@/components/Logo.vue'
import RunTimeline from '@/components/RunTimeline.vue'
import { useDevices } from '@/composables/useDevices'
import { useLive } from '@/composables/useLive'
import { useTween } from '@/composables/useTween'
import { api } from '@/lib/api'
import { eurFromWh, kwh, money, num, pct, watts } from '@/lib/format'
import type { Meter, MeterCosts, Overview } from '@/lib/types'

const { t, locale } = useI18n()
const live = useLive()
const { list, color } = useDevices()
const now = useNow({ scheduler: (cb) => useIntervalFn(cb, 1000) })

const ov = useQuery({ queryKey: ['overview', 30, null], queryFn: () => api.get<Overview>('/api/overview?days=30'), refetchInterval: 5 * 60_000 })
const meters = useQuery({ queryKey: ['meters'], queryFn: () => api.get<Meter[]>('/api/meters'), staleTime: 60 * 60_000 })
const elec = computed(() => (meters.data.value ?? []).find((m) => m.kind === 'electricity' && !m.archived))
const costs = useQuery({
  queryKey: computed(() => ['meter-costs', elec.value?.id]),
  queryFn: () => api.get<MeterCosts>(`/api/meters/${elec.value!.id}/costs`),
  enabled: computed(() => !!elec.value), refetchInterval: 30 * 60_000,
})

const k = computed(() => ov.data.value?.kpi)
const price = computed(() => ov.data.value?.price ?? null)
const total = computed(() => live.snapshot.value?.total_w ?? null)
const totalTween = useTween(total, 450)
const balance = computed(() => costs.data.value?.billing?.balance ?? null)
const todayDelta = computed(() => (k.value?.yesterday_same_time_wh ? k.value.today_wh / k.value.yesterday_same_time_wh - 1 : null))
const drawing = computed(() => {
  const devs = live.snapshot.value?.devices ?? {}, tot = total.value || 0
  return list.value.map((d) => ({ id: d.id, name: d.name, w: devs[d.id]?.w ?? 0 }))
    .filter((d) => d.w >= 0.5).sort((a, b) => b.w - a.w).slice(0, 7)
    .map((d) => ({ ...d, share: tot ? d.w / tot : 0 }))
})
const clock = computed(() => new Intl.DateTimeFormat(locale.value, { hour: '2-digit', minute: '2-digit' }).format(now.value))
const date = computed(() => new Intl.DateTimeFormat(locale.value, { weekday: 'long', day: 'numeric', month: 'long' }).format(now.value))
const todayIso = computed(() => now.value.toLocaleDateString('sv-SE'))

// controls fade out after 4 s without input, the cursor with them
const { idle } = useIdle(4000)
const { isFullscreen, toggle: toggleFullscreen, isSupported: fsSupported } = useFullscreen()
const wake = useWakeLock()
onMounted(() => { if (wake.isSupported.value) wake.request('screen').catch(() => {}) })
onBeforeUnmount(() => { if (wake.isActive.value) wake.release() })

// burn-in: a slow 2 px orbit, one step per minute
const shift = ref({ x: 0, y: 0 })
const orbit = [[0, 0], [1, 0], [2, 1], [1, 2], [0, 2], [-1, 1], [-2, 0], [-1, -1]] as const
let step = 0
useIntervalFn(() => { step = (step + 1) % orbit.length; shift.value = { x: orbit[step]![0], y: orbit[step]![1] } }, 60_000)

// nightly reload at 04:00
let reloadTimer: ReturnType<typeof setTimeout> | undefined
onMounted(() => {
  const n = new Date(), at = new Date(n); at.setHours(4, 0, 0, 0)
  if (at <= n) at.setDate(at.getDate() + 1)
  reloadTimer = setTimeout(() => window.location.reload(), at.getTime() - n.getTime())
})
onBeforeUnmount(() => clearTimeout(reloadTimer))
</script>

<template>
  <div class="min-h-dvh bg-background text-foreground" :class="idle ? 'cursor-none' : ''">
    <div class="mx-auto flex min-h-dvh max-w-[1600px] flex-col gap-8 px-6 py-6 transition-[translate] duration-1000 md:px-10 md:py-8"
         :style="{ translate: `${shift.x}px ${shift.y}px` }">
      <!-- top bar -->
      <header class="flex items-center gap-4">
        <Logo />
        <span class="text-base font-semibold tracking-tight">tiris</span>
        <span class="flex items-center gap-2 text-sm text-caption"><LiveDot :on="live.connected.value" :beat="live.snapshot.value?.at" />
          {{ live.connected.value ? t('app.liveNow') : t('app.liveOff') }}</span>
        <span class="flex-1" aria-hidden="true" />
        <div class="flex items-center gap-1 transition-opacity duration-500" :class="idle ? 'pointer-events-none opacity-0' : 'opacity-100'">
          <span v-if="wake.isSupported.value" class="mr-2 flex items-center gap-1.5 text-xs text-caption" :title="t('wall.wakeHint')">
            <Sun class="size-3.5" aria-hidden="true" />{{ wake.isActive.value ? t('wall.awake') : t('wall.mayDim') }}
          </span>
          <button v-if="fsSupported" type="button" class="grid size-9 place-items-center rounded-md text-caption hover:bg-muted hover:text-foreground"
                  :aria-label="isFullscreen ? t('wall.exitFullscreen') : t('wall.fullscreen')" @click="toggleFullscreen()">
            <Minimize v-if="isFullscreen" class="size-4" aria-hidden="true" /><Maximize v-else class="size-4" aria-hidden="true" />
          </button>
          <RouterLink to="/" class="flex h-9 items-center gap-1.5 rounded-md px-2.5 text-sm text-caption hover:bg-muted hover:text-foreground">
            <ArrowLeft class="size-4" aria-hidden="true" />{{ t('wall.back') }}
          </RouterLink>
        </div>
        <div class="text-right">
          <p class="text-2xl font-semibold tabular">{{ clock }}</p>
          <p class="text-sm text-caption">{{ date }}</p>
        </div>
      </header>

      <!-- now + who draws -->
      <section class="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
        <div class="min-w-0">
          <p class="text-sm font-medium text-caption">{{ t('overview.now') }}</p>
          <p class="mt-2 text-5xl font-semibold tabular xl:text-7xl">
            {{ totalTween == null ? '–' : num(totalTween, totalTween < 100 ? 1 : 0) }}<span class="ml-2 text-2xl font-medium tracking-normal text-caption">W</span>
          </p>
          <p v-if="total != null && price != null" class="mt-2 text-lg text-muted-foreground tabular">{{ t('overview.atThisLoad', { value: money(total * 24 / 1000 * price) }) }}</p>
          <LiveSpark class="mt-6" :points="live.total.value.slice(-450)" :height="96" />
        </div>
        <div class="min-w-0">
          <p class="mb-3 text-sm font-medium text-caption">{{ t('app.drawing') }}</p>
          <ul class="flex flex-col gap-3">
            <li v-for="d in drawing" :key="d.id">
              <div class="flex items-baseline gap-3 text-lg">
                <span class="size-3 shrink-0 self-center rounded-sm" :style="{ background: color(d.id) }" aria-hidden="true" />
                <span class="truncate">{{ d.name }}</span><span class="flex-1" aria-hidden="true" />
                <span class="font-semibold tabular">{{ watts(d.w) }}</span>
              </div>
              <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-border" aria-hidden="true">
                <div class="h-full origin-left rounded-full transition-transform duration-(--ease-settle-ms) ease-settle" :style="{ background: color(d.id), transform: `scaleX(${Math.max(0.02, d.share).toFixed(3)})` }" />
              </div>
            </li>
            <li v-if="!drawing.length" class="text-lg text-caption">{{ t('app.nothingDrawing') }}</li>
          </ul>
        </div>
      </section>

      <!-- today, month, forecast, bill -->
      <section class="grid grid-cols-2 gap-x-8 gap-y-6 border-y border-border py-6 lg:grid-cols-4 lg:divide-x lg:divide-border">
        <div class="lg:pr-6">
          <p class="text-sm font-medium text-caption">{{ t('common.today') }}</p>
          <p class="mt-1 text-2xl font-semibold tabular">{{ kwh(k?.today_wh, 2) }}<span class="ml-1 text-base font-medium tracking-normal text-caption">kWh</span></p>
          <p class="text-sm text-muted-foreground tabular">
            <template v-if="price != null">{{ eurFromWh(k?.today_wh, price) }}</template>
            <template v-if="todayDelta != null"> · <span :class="todayDelta > 0 ? 'text-bad' : 'text-good'">{{ (todayDelta > 0 ? '+' : '') + pct(todayDelta) }}</span> {{ t('wall.vsYesterday') }}</template>
          </p>
        </div>
        <div class="lg:px-6">
          <p class="text-sm font-medium text-caption">{{ t('wall.month') }}</p>
          <p class="mt-1 text-2xl font-semibold tabular">{{ kwh(k?.mtd_wh, 0) }}<span class="ml-1 text-base font-medium tracking-normal text-caption">kWh</span></p>
          <p v-if="price != null" class="text-sm text-muted-foreground tabular">{{ eurFromWh(k?.mtd_wh, price) }}</p>
        </div>
        <div class="lg:px-6">
          <p class="text-sm font-medium text-caption">{{ t('wall.forecast') }}</p>
          <p class="mt-1 text-2xl font-semibold tabular">{{ kwh(k?.forecast_month_wh, 0) }}<span class="ml-1 text-base font-medium tracking-normal text-caption">kWh</span></p>
          <p v-if="price != null" class="text-sm text-muted-foreground tabular">{{ eurFromWh(k?.forecast_month_wh, price) }}</p>
        </div>
        <div class="lg:pl-6">
          <p class="text-sm font-medium text-caption">{{ t('wall.bill') }}</p>
          <template v-if="balance != null">
            <p class="mt-1 text-2xl font-semibold tabular" :class="balance > 10 ? 'text-warn' : 'text-good'">{{ money(Math.abs(balance), 0) }}</p>
            <p class="text-sm text-muted-foreground">{{ balance > 10 ? t('wall.backPayment') : balance < -10 ? t('wall.refund') : t('wall.balanced') }}</p>
          </template>
          <p v-else class="mt-1 text-sm text-caption">{{ t('wall.noBill') }}</p>
        </div>
      </section>

      <!-- what ran today -->
      <section class="min-h-0">
        <p class="mb-3 text-sm font-medium text-caption">{{ t('events.title') }}</p>
        <RunTimeline :day="todayIso" compact />
      </section>
    </div>
  </div>
</template>
