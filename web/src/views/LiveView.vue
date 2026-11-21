<script setup lang="ts">
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import { useIntervalFn } from '@vueuse/core'
import type { EChartsOption } from 'echarts'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import EChart from '@/components/charts/EChart.vue'
import Sparkline from '@/components/charts/Sparkline.vue'
import PageHeader from '@/components/PageHeader.vue'
import Panel from '@/components/Panel.vue'
import StateMessage from '@/components/StateMessage.vue'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useChartTheme } from '@/composables/useChartTheme'
import { useLive } from '@/composables/useLive'
import { api } from '@/lib/api'
import { dayLong, money, NBSP, num, time, watts } from '@/lib/format'
import type { Overview, SeriesResponse } from '@/lib/types'

const { t } = useI18n()
const theme = useChartTheme()
const live = useLive()
const WINDOWS = [60, 300, 900] as const
const win = ref<number>(300)

const meta = useQuery({ queryKey: ['overview', 7, null], queryFn: () => api.get<Overview>('/api/overview?days=7'), staleTime: 5 * 60_000 })
const price = computed(() => meta.data.value?.price ?? null)
const devices = computed(() => meta.data.value?.devices ?? [])

const snap = computed(() => live.snapshot.value)
const totalW = computed(() => snap.value?.total_w ?? null)
const avgV = computed(() => {
  const v = Object.values(snap.value?.devices ?? {}).map((d) => d.v).filter(Boolean)
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
})
const windowPts = computed(() => live.total.value.filter((p) => p.t >= live.now.value - win.value))
const span = computed(() => {
  const p = windowPts.value
  if (!p.length) return null
  return { lo: Math.min(...p.map((x) => x.w)), hi: Math.max(...p.map((x) => x.w)) }
})

function lineOption(points: [number, number][], opts: { from: number; to: number; band?: [number, number][]; seconds?: boolean }): EChartsOption {
  const th = theme.value
  const accent = th.token('chart-1')
  return {
    ...th.base,
    grid: { left: 8, right: 64, top: 28, bottom: 4, containLabel: true },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: th.token('caption') } },
      formatter: (ps: unknown) => {
        const arr = ps as { value: [number, number]; seriesName: string }[]
        const head = time(arr[0]!.value[0] / 1000, opts.seconds)
        return [`<b>${head}</b>`, ...arr.map((p) => `${p.seriesName}: ${watts(p.value[1])}`)].join('<br>')
      } },
    xAxis: { type: 'time', min: opts.from * 1000, max: opts.to * 1000, axisLine: th.base.axisCommon.axisLine, splitLine: { show: false },
      axisLabel: { ...th.base.axisCommon.axisLabel, hideOverlap: true, formatter: (v: number) => time(v / 1000, opts.seconds) } },
    yAxis: { type: 'value', min: 0, splitLine: th.base.axisCommon.splitLine, name: 'W', nameGap: 12,
      nameTextStyle: { color: th.token('caption'), align: 'left' },
      axisLabel: { ...th.base.axisCommon.axisLabel, formatter: (v: number) => (v >= 1000 ? `${num(v / 1000, 1)}k` : num(v)) } },
    series: [
      ...(opts.band ? [{ type: 'line' as const, name: t('live.peak'), data: opts.band.map(([x, y]) => [x * 1000, y]), showSymbol: false,
        lineStyle: { width: 0 }, areaStyle: { color: accent, opacity: 0.12 }, connectNulls: false, z: 1 }] : []),
      { type: 'line', name: opts.band ? t('live.avg') : t('live.total'), data: points.map(([x, y]) => [x * 1000, y]), showSymbol: false,
        lineStyle: { width: 2, color: accent }, areaStyle: { color: accent, opacity: 0.08 }, connectNulls: false, z: 2,
        endLabel: opts.band ? undefined : { show: true, color: th.token('foreground'), fontWeight: 600, formatter: (p: { value?: unknown }) => watts((p.value as [number, number])[1]) } },
    ],
  }
}

const liveOption = computed(() => {
  const to = live.now.value
  return lineOption(windowPts.value.map((p) => [p.t, p.w]), { from: to - win.value, to, seconds: win.value <= 60 })
})

// status per device: idle (0 W), standby (below 1.6 x base load, min 3 W), active
function status(w: number | undefined, base: number | null) {
  if (w == null) return 'offline'
  if (w < 0.5) return 'idle'
  if (w < Math.max(3, (base ?? 0) * 1.6)) return 'standby'
  return 'on'
}
const order = ref<string[]>([])
function reorder() {
  const avg = (id: string) => { const a = (live.perDevice.value[id] ?? []).slice(-30); return a.length ? a.reduce((s, p) => s + p.w, 0) / a.length : 0 }
  order.value = [...devices.value].sort((a, b) => avg(b.id) - avg(a.id) || a.name.localeCompare(b.name)).map((d) => d.id)
}
useIntervalFn(reorder, 10_000)   // cards re-sort every 10 s, not on every sample
watch(() => devices.value.length, reorder, { immediate: true })
const cards = computed(() => {
  const byId = Object.fromEntries(devices.value.map((d) => [d.id, d]))
  const tot = totalW.value || 0
  return (order.value.length ? order.value : devices.value.map((d) => d.id)).filter((id) => byId[id]).map((id) => {
    const m = byId[id]!, l = snap.value?.devices[id]
    return { ...m, live: l, st: status(l?.w, m.base_w), share: l && tot > 0 ? l.w / tot : 0,
      spark: (live.perDevice.value[id] ?? []).slice(-150).map((p) => p.w) }
  })
})
const activeCount = computed(() => cards.value.filter((c) => c.st === 'on').length)

// --- day view from the minute aggregate
const today = () => new Date().toLocaleDateString('sv-SE')
const day = ref(today())
const dayRange = computed(() => {
  const [y, m, d] = day.value.split('-').map(Number)
  const from = new Date(y!, m! - 1, d!), to = new Date(y!, m! - 1, d! + 1)
  return { from: from.getTime() / 1000, to: to.getTime() / 1000, iso: [from.toISOString(), to.toISOString()] }
})
const dayQ = useQuery({
  queryKey: computed(() => ['series-day', day.value]),
  queryFn: () => api.get<SeriesResponse>(`/api/series?from=${encodeURIComponent(dayRange.value.iso[0]!)}&to=${encodeURIComponent(dayRange.value.iso[1]!)}&bucket=1m`),
  refetchInterval: () => (day.value === today() ? 60_000 : false),
  placeholderData: (p) => p,
})
const dayStats = computed(() => {
  const pts = dayQ.data.value?.points ?? []
  if (!pts.length) return null
  const wh = pts.reduce((s, p) => s + (p[5] ?? 0), 0)
  // Extremes only from minutes where (nearly) every plug was measured; partial minutes read too low or too high.
  const full = Math.max(...pts.map((p) => p[6]))
  const complete = pts.filter((p) => p[6] >= full * 0.8)
  let peak = complete[0]!, low = complete[0]!
  for (const p of complete) { if (p[3] > peak[3]) peak = p; if (p[1] < low[1]) low = p }
  return { wh, minutes: pts.length, avg: pts.reduce((s, p) => s + p[1], 0) / pts.length, peak, low }
})
const dayOption = computed(() => {
  const pts = dayQ.data.value?.points ?? []
  // break the line where minutes are missing (tiris was not running)
  const line: [number, number][] = [], band: [number, number][] = []
  pts.forEach((p, i) => {
    if (i && p[0] - pts[i - 1]![0] > 180) { line.push([p[0] - 60, NaN]); band.push([p[0] - 60, NaN]) }
    line.push([p[0], p[1]]); band.push([p[0], p[3]])
  })
  return lineOption(line, { from: dayRange.value.from, to: dayRange.value.to, band })
})
function shiftDay(n: number) {
  const [y, m, d] = day.value.split('-').map(Number)
  const s = new Date(y!, m! - 1, d! + n).toLocaleDateString('sv-SE')
  if (s <= today()) day.value = s
}
const dayLabel = computed(() => (day.value === today() ? t('common.today') : dayLong(day.value)))
const perHour = (w: number | null | undefined) => (w == null || price.value == null ? null : (w / 1000) * price.value)
</script>

<template>
  <PageHeader :title="t('live.title')" />

  <StateMessage v-if="!live.enabled.value" kind="setup" :title="t('states.noTapoTitle')" :body="t('states.noTapoBody')" />

  <div v-else class="flex flex-col gap-4">
    <section class="grid gap-6 rounded-lg border border-border bg-card p-6 lg:grid-cols-[minmax(240px,0.8fr)_2fr]">
      <div class="flex min-w-0 flex-col">
        <p class="flex items-center gap-2 text-sm text-muted-foreground">
          <span class="size-2 shrink-0 rounded-full" :class="live.connected.value ? 'bg-good-fill' : 'bg-caption'" aria-hidden="true" />
          {{ live.connected.value ? t('live.connected', { s: snap?.interval_s ?? 2 }) : t('live.connecting') }}
        </p>
        <p class="mt-2 text-4xl font-semibold tabular" aria-live="off">
          {{ totalW == null ? '–' : num(totalW, totalW < 100 ? 1 : 0) }}<span class="ml-2 text-lg font-medium text-muted-foreground">W</span>
        </p>
        <div v-if="price != null && totalW != null" class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span>{{ t('live.perHour', { value: money(perHour(totalW)) }) }}</span>
          <span>{{ t('live.perDay', { value: money(perHour(totalW)! * 24) }) }}</span>
          <span>{{ t('live.perMonth', { value: money(perHour(totalW)! * 24 * 30.4, 0) }) }}</span>
        </div>
        <div class="min-h-6 flex-1" aria-hidden="true" />
        <dl class="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <div><dt class="text-muted-foreground">{{ t('live.voltage') }}</dt><dd class="text-md font-semibold tabular">{{ avgV ? `${num(avgV, 1)}${NBSP}V` : '–' }}</dd></div>
          <div><dt class="text-muted-foreground">{{ t('live.online') }}</dt><dd class="text-md font-semibold tabular">{{ snap?.online ?? '–' }}/{{ snap?.known ?? '–' }}</dd></div>
          <div><dt class="text-muted-foreground">{{ t('live.active') }}</dt><dd class="text-md font-semibold tabular">{{ activeCount }}</dd></div>
          <div v-if="span"><dt class="text-muted-foreground">{{ t('live.span', { window: t(`live.window.m${win / 60}`) }) }}</dt>
            <dd class="text-md font-semibold tabular">{{ watts(span.lo) }} – {{ watts(span.hi) }}</dd></div>
        </dl>
      </div>
      <div class="min-w-0">
        <div class="mb-1 flex items-center justify-between gap-2">
          <h2 class="font-medium">{{ t('live.total') }}</h2>
          <Tabs :model-value="String(win)" @update:model-value="(v) => (win = Number(v))">
            <TabsList>
              <TabsTrigger v-for="w in WINDOWS" :key="w" :value="String(w)">{{ t(`live.window.m${w / 60}`) }}</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        <EChart :option="liveOption" :height="260" :label="t('live.total')" />
      </div>
    </section>

    <section class="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
      <article v-for="c in cards" :key="c.id" class="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-card px-4 py-3.5">
        <header class="flex items-start gap-2 text-sm">
          <span class="mt-1.5 size-2 shrink-0 rounded-full" :style="{ background: theme.slotColor(c.slot) }" aria-hidden="true" />
          <RouterLink :to="`/devices/${c.id}`" class="min-w-0 flex-1 font-medium [overflow-wrap:anywhere] hover:underline">{{ c.name }}</RouterLink>
          <span class="shrink-0 rounded-full px-2 py-px text-xs"
                :class="c.st === 'on' ? 'bg-selection font-medium text-foreground' : 'bg-muted text-muted-foreground'">{{ t(`live.status.${c.st}`) }}</span>
        </header>
        <p class="text-2xl font-semibold tabular" :class="c.st === 'idle' || c.st === 'offline' ? 'text-caption' : ''">{{ c.live ? watts(c.live.w) : '–' }}</p>
        <Sparkline :values="c.spark" :width="240" :height="32" class="w-full" />
        <div class="h-1 overflow-hidden rounded-full bg-muted" :aria-label="`${num(c.share * 100)} %`">
          <div class="h-full rounded-full bg-primary transition-[width] duration-300" :style="{ width: `${(c.share * 100).toFixed(1)}%` }" />
        </div>
        <dl class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          <div class="flex justify-between gap-2"><dt class="text-caption">{{ t('live.current') }}</dt><dd class="tabular text-muted-foreground">{{ c.live ? `${num(c.live.a, 2)}${NBSP}A` : '–' }}</dd></div>
          <div class="flex justify-between gap-2"><dt class="text-caption">V</dt><dd class="tabular text-muted-foreground">{{ c.live ? num(c.live.v, 1) : '–' }}</dd></div>
          <div class="flex justify-between gap-2"><dt class="text-caption" :title="t('live.pf')">cos φ</dt><dd class="tabular text-muted-foreground">{{ c.live?.pf != null ? num(c.live.pf, 2) : '–' }}</dd></div>
          <div v-if="price != null" class="flex justify-between gap-2"><dt class="text-caption">{{ t('live.cost') }}</dt>
            <dd class="tabular text-muted-foreground">{{ c.live ? `${num(perHour(c.live.w)! * 100, 2)}${NBSP}ct/h` : '–' }}</dd></div>
        </dl>
      </article>
    </section>

    <Panel :title="t('live.day', { day: dayLabel })" :description="t('live.daySub')">
      <template #actions>
        <Button type="button" variant="outline" size="icon-sm" :aria-label="t('live.prevDay')" @click="shiftDay(-1)"><ChevronLeft class="size-4" /></Button>
        <input v-model="day" type="date" :max="today()" class="h-8 rounded-md border border-input bg-card px-2 text-sm" :aria-label="t('common.date')" />
        <Button type="button" variant="outline" size="icon-sm" :aria-label="t('live.nextDay')" :disabled="day >= today()" @click="shiftDay(1)"><ChevronRight class="size-4" /></Button>
      </template>
      <dl v-if="dayStats" class="mb-3 grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
        <div><dt class="text-muted-foreground">{{ t('live.measured') }}</dt><dd class="text-md font-semibold tabular">{{ num(dayStats.wh / 1000, 2) }}{{ NBSP }}kWh</dd>
          <dd class="text-caption">{{ dayStats.minutes }} min<template v-if="price != null">, {{ money(dayStats.wh / 1000 * price) }}</template></dd></div>
        <div><dt class="text-muted-foreground">{{ t('live.avg') }}</dt><dd class="text-md font-semibold tabular">{{ watts(dayStats.avg) }}</dd></div>
        <div><dt class="text-muted-foreground">{{ t('live.peak') }}</dt><dd class="text-md font-semibold tabular">{{ watts(dayStats.peak[3]) }}</dd>
          <dd class="text-caption">{{ t('live.at', { time: time(dayStats.peak[0]) }) }}</dd></div>
        <div><dt class="text-muted-foreground">{{ t('live.lowest') }}</dt><dd class="text-md font-semibold tabular">{{ watts(dayStats.low[1]) }}</dd>
          <dd class="text-caption">{{ t('live.at', { time: time(dayStats.low[0]) }) }}</dd></div>
      </dl>
      <p v-if="dayQ.isSuccess.value && !dayStats" class="py-8 text-center text-sm text-muted-foreground">{{ t('live.noDay') }}</p>
      <EChart v-else-if="dayStats" :option="dayOption" :height="260" :label="t('live.day', { day: dayLabel })" />
      <div v-else class="h-[260px] animate-pulse rounded-md bg-muted" />
    </Panel>
  </div>
</template>
