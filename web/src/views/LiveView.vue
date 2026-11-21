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
import Section from '@/components/Section.vue'
import Segmented from '@/components/Segmented.vue'
import StateMessage from '@/components/StateMessage.vue'
import { Button } from '@/components/ui/button'
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
const winOptions = computed(() => WINDOWS.map((w) => ({ value: w, label: t(`live.window.m${w / 60}`) })))

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
  const accent = th.token('primary')
  return {
    ...th.base,
    grid: { left: 0, right: 0, top: 8, bottom: 0, containLabel: true },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: th.token('caption') } },
      formatter: (ps: unknown) => {
        const arr = ps as { value: [number, number]; seriesName: string }[]
        const head = time(arr[0]!.value[0] / 1000, opts.seconds)
        return [`<b>${head}</b>`, ...arr.map((p) => `${p.seriesName}: ${watts(p.value[1])}`)].join('<br>')
      } },
    xAxis: { type: 'time', min: opts.from * 1000, max: opts.to * 1000, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { color: th.token('caption'), fontSize: 11, hideOverlap: true, formatter: (v: number) => time(v / 1000, opts.seconds) } },
    yAxis: { type: 'value', min: 0, position: 'right', splitNumber: 3, splitLine: th.base.axisCommon.splitLine,
      axisLabel: { color: th.token('caption'), fontSize: 11, formatter: (v: number) => (v >= 1000 ? `${num(v / 1000, 1)}${NBSP}kW` : `${num(v)}${NBSP}W`) } },
    series: [
      ...(opts.band ? [{ type: 'line' as const, name: t('live.peak'), data: opts.band.map(([x, y]) => [x * 1000, y]), showSymbol: false,
        lineStyle: { width: 0 }, areaStyle: { color: accent, opacity: 0.12 }, connectNulls: false, z: 1 }] : []),
      { type: 'line', name: opts.band ? t('live.avg') : t('live.total'), data: points.map(([x, y]) => [x * 1000, y]), showSymbol: false,
        lineStyle: { width: 1.5, color: accent }, connectNulls: false, z: 2,
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: `${accent}38` }, { offset: 1, color: `${accent}00` }] } } },
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
const drawing = computed(() => cards.value.filter((c) => c.st === 'on' || c.st === 'standby'))
const resting = computed(() => cards.value.filter((c) => c.st === 'idle' || c.st === 'offline'))

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
  <div class="mb-7 flex h-9 items-center justify-between gap-3">
    <h1 class="font-semibold">{{ t('live.title') }}</h1>
    <p v-if="live.enabled.value" class="flex items-center gap-2 text-sm text-caption">
      <span class="size-1.5 shrink-0 rounded-full" :class="live.connected.value ? 'bg-good-fill' : 'bg-caption'" aria-hidden="true" />
      {{ live.connected.value ? t('live.connected', { s: snap?.interval_s ?? 2 }) : t('live.connecting') }}
    </p>
  </div>

  <StateMessage v-if="!live.enabled.value" kind="setup" :title="t('states.noTapoTitle')" :body="t('states.noTapoBody')" />

  <div v-else class="flex flex-col divide-y divide-border">
    <section class="pb-8">
      <div class="flex flex-wrap items-end justify-between gap-x-10 gap-y-5">
        <div class="min-w-0">
          <p class="text-xs font-medium text-caption">{{ t('live.total') }}</p>
          <p class="mt-2 text-4xl font-semibold tabular" aria-live="off">
            {{ totalW == null ? '–' : num(totalW, totalW < 100 ? 1 : 0) }}<span class="ml-1 text-lg font-medium tracking-normal text-caption">W</span>
          </p>
          <p v-if="price != null && totalW != null" class="mt-2 text-sm text-muted-foreground tabular">
            {{ t('live.perHour', { value: money(perHour(totalW)) }) }} · {{ t('live.perDay', { value: money(perHour(totalW)! * 24) }) }} · {{ t('live.perMonth', { value: money(perHour(totalW)! * 24 * 30.4, 0) }) }}
          </p>
        </div>
        <dl class="grid grid-cols-2 gap-x-8 gap-y-3 text-sm sm:flex sm:gap-0 sm:divide-x sm:divide-border">
          <div class="sm:px-6 sm:first:pl-0"><dt class="text-xs text-caption">{{ t('live.voltage') }}</dt><dd class="mt-1 font-semibold tabular">{{ avgV ? `${num(avgV, 1)}${NBSP}V` : '–' }}</dd></div>
          <div class="sm:px-6"><dt class="text-xs text-caption">{{ t('live.online') }}</dt><dd class="mt-1 font-semibold tabular">{{ snap?.online ?? '–' }}/{{ snap?.known ?? '–' }}</dd></div>
          <div class="sm:px-6"><dt class="text-xs text-caption">{{ t('live.active') }}</dt><dd class="mt-1 font-semibold tabular">{{ activeCount }}</dd></div>
          <div v-if="span" class="sm:pl-6"><dt class="text-xs text-caption">{{ t('live.span', { window: t(`live.window.m${win / 60}`) }) }}</dt>
            <dd class="mt-1 font-semibold tabular">{{ watts(span.lo) }} – {{ watts(span.hi) }}</dd></div>
        </dl>
      </div>
      <div class="mb-3 mt-8 flex items-center justify-end">
        <Segmented v-model="win" :options="winOptions" :label="t('live.windowLabel')" />
      </div>
      <EChart :option="liveOption" :height="240" :label="t('live.total')" />
    </section>

    <Section :title="t('live.devices')" :summary="t('live.devicesSub')">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-xs text-caption">
              <th class="h-8 pr-3 text-left font-medium">{{ t('overview.col.device') }}</th>
              <th class="px-3 text-right font-medium">{{ t('overview.col.now') }}</th>
              <th class="hidden px-3 text-left font-medium md:table-cell">{{ t('live.last5') }}</th>
              <th class="hidden px-3 text-right font-medium sm:table-cell">{{ t('overview.col.share') }}</th>
              <th class="hidden px-3 text-right font-medium lg:table-cell">{{ t('live.current') }}</th>
              <th class="hidden px-3 text-right font-medium lg:table-cell">V</th>
              <th class="hidden px-3 text-right font-medium lg:table-cell" :title="t('live.pf')">cos φ</th>
              <th v-if="price != null" class="pl-3 text-right font-medium">{{ t('live.cost') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in drawing" :key="c.id" class="h-12 border-t border-border">
              <td class="max-w-64 pr-3">
                <RouterLink :to="`/devices/${c.id}`" class="flex min-w-0 items-center gap-2.5 font-medium hover:underline">
                  <span class="size-1.5 shrink-0 rounded-full bg-good-fill" aria-hidden="true" />
                  <span class="truncate" :title="c.name">{{ c.name }}</span>
                  <span v-if="c.st === 'standby'" class="shrink-0 text-xs font-normal text-caption">{{ t('live.status.standby') }}</span>
                </RouterLink>
              </td>
              <td class="px-3 text-right text-md font-semibold tabular">{{ c.live ? watts(c.live.w) : '–' }}</td>
              <td class="hidden px-3 md:table-cell"><Sparkline :values="c.spark" :width="160" :height="26" /></td>
              <td class="hidden px-3 sm:table-cell">
                <span class="flex items-center justify-end gap-2.5">
                  <span class="h-1 w-16 overflow-hidden rounded-full bg-border" aria-hidden="true">
                    <span class="block h-full origin-left rounded-full bg-primary transition-transform duration-(--ease-settle-ms) ease-settle" :style="{ transform: `scaleX(${c.share.toFixed(3)})` }" />
                  </span>
                  <span class="w-10 text-right text-muted-foreground tabular">{{ num(c.share * 100) }}{{ NBSP }}%</span>
                </span>
              </td>
              <td class="hidden px-3 text-right text-muted-foreground tabular lg:table-cell">{{ c.live ? `${num(c.live.a, 2)}${NBSP}A` : '–' }}</td>
              <td class="hidden px-3 text-right text-muted-foreground tabular lg:table-cell">{{ c.live ? num(c.live.v, 1) : '–' }}</td>
              <td class="hidden px-3 text-right text-muted-foreground tabular lg:table-cell">{{ c.live?.pf != null ? num(c.live.pf, 2) : '–' }}</td>
              <td v-if="price != null" class="pl-3 text-right tabular">{{ c.live ? `${num(perHour(c.live.w)! * 100, 2)}${NBSP}ct/h` : '–' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="resting.length" class="mt-4 text-sm text-caption">
        <span class="font-medium text-muted-foreground">{{ t('live.resting', { n: resting.length }) }}</span>
        <template v-for="(c, i) in resting" :key="c.id">
          {{ i ? ', ' : ' ' }}<RouterLink :to="`/devices/${c.id}`" class="hover:text-foreground hover:underline">{{ c.name }}</RouterLink>
        </template>
      </p>
    </Section>

    <Section :title="t('live.day', { day: dayLabel })" :summary="t('live.daySub')">
      <template #actions>
        <div class="flex items-center gap-1">
          <Button type="button" variant="ghost" size="icon-sm" :aria-label="t('live.prevDay')" @click="shiftDay(-1)"><ChevronLeft class="size-4" /></Button>
          <input v-model="day" type="date" :max="today()" class="h-8 rounded-md border border-input bg-background px-2 text-sm" :aria-label="t('common.date')" />
          <Button type="button" variant="ghost" size="icon-sm" :aria-label="t('live.nextDay')" :disabled="day >= today()" @click="shiftDay(1)"><ChevronRight class="size-4" /></Button>
        </div>
      </template>
      <dl v-if="dayStats" class="mb-5 grid grid-cols-2 gap-x-8 gap-y-3 text-sm sm:flex sm:gap-0 sm:divide-x sm:divide-border">
        <div class="sm:px-6 sm:first:pl-0"><dt class="text-xs text-caption">{{ t('live.measured') }}</dt><dd class="mt-1 font-semibold tabular">{{ num(dayStats.wh / 1000, 2) }}{{ NBSP }}kWh</dd>
          <dd class="text-xs text-caption">{{ dayStats.minutes }} min<template v-if="price != null">, {{ money(dayStats.wh / 1000 * price) }}</template></dd></div>
        <div class="sm:px-6"><dt class="text-xs text-caption">{{ t('live.avg') }}</dt><dd class="mt-1 font-semibold tabular">{{ watts(dayStats.avg) }}</dd></div>
        <div class="sm:px-6"><dt class="text-xs text-caption">{{ t('live.peak') }}</dt><dd class="mt-1 font-semibold tabular">{{ watts(dayStats.peak[3]) }}</dd>
          <dd class="text-xs text-caption">{{ t('live.at', { time: time(dayStats.peak[0]) }) }}</dd></div>
        <div class="sm:pl-6"><dt class="text-xs text-caption">{{ t('live.lowest') }}</dt><dd class="mt-1 font-semibold tabular">{{ watts(dayStats.low[1]) }}</dd>
          <dd class="text-xs text-caption">{{ t('live.at', { time: time(dayStats.low[0]) }) }}</dd></div>
      </dl>
      <p v-if="dayQ.isSuccess.value && !dayStats" class="py-8 text-center text-sm text-muted-foreground">{{ t('live.noDay') }}</p>
      <EChart v-else-if="dayStats" :option="dayOption" :height="240" :label="t('live.day', { day: dayLabel })" />
      <div v-else class="h-[240px] animate-pulse rounded-md bg-muted" />
    </Section>
  </div>
</template>
