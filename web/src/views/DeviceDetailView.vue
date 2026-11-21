<script setup lang="ts">
import { ArrowLeft } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import EChart from '@/components/charts/EChart.vue'
import Section from '@/components/Section.vue'
import Segmented from '@/components/Segmented.vue'
import StateMessage from '@/components/StateMessage.vue'
import { useChartTheme } from '@/composables/useChartTheme'
import { api } from '@/lib/api'
import { dayShort, duration, kwh, money, NBSP, num, pct, time, watts } from '@/lib/format'
import type { SeriesResponse } from '@/lib/types'

interface Analysis {
  device: { id: string; name: string; model: string; room: string | null; category: string | null; protected: boolean }
  range: { from: string; to: string; hours: number; resolution: 'raw' | '1m' | '5min'; points: number }
  price: number | null
  energy_wh: number
  power: { avg: number | null; max: number | null; min: number | null; base: number }
  voltage: { avg: number | null; min: number | null; max: number | null }
  cycles: { count: number; duty: number | null; median_s: number | null; max_s: number | null; threshold_w: number } | null
  daily: { day: string; wh: number }[]
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const theme = useChartTheme()
const id = computed(() => String(route.params.id))
const RANGES = [24, 168, 720] as const
const hours = computed(() => { const h = Number(route.query.h); return RANGES.includes(h as never) ? h : 24 })
const setHours = (h: number) => router.replace({ query: { ...route.query, h: String(h) } })
const hourOptions = computed(() => [{ value: 24, label: t('detail.range.h24') }, { value: 168, label: t('detail.range.d7') }, { value: 720, label: t('detail.range.d30') }])

const a = useQuery({
  queryKey: computed(() => ['analysis', id.value, hours.value]),
  queryFn: () => api.get<Analysis>(`/api/devices/${encodeURIComponent(id.value)}/analysis?hours=${hours.value}`),
  placeholderData: (p) => p, refetchInterval: 60_000,
})
const range = computed(() => {
  const to = Date.now(), from = to - hours.value * 3600_000
  return { from: from / 1000, to: to / 1000, iso: [new Date(from).toISOString(), new Date(to).toISOString()] as const }
})
const s = useQuery({
  queryKey: computed(() => ['series-device', id.value, hours.value]),
  queryFn: () => api.get<SeriesResponse>(`/api/series?from=${encodeURIComponent(range.value.iso[0])}&device=${encodeURIComponent(id.value)}`),
  placeholderData: (p) => p, refetchInterval: 60_000,
})
const d = computed(() => a.data.value)
const price = computed(() => d.value?.price ?? null)
const perDay = computed(() => (d.value?.cycles ? d.value.cycles.count / (hours.value / 24) : null))

function timeLine(points: [number, number][], band: [number, number][] | null, unit: 'W' | 'V', min?: number, max?: number, from?: number): EChartsOption {
  const th = theme.value, c = th.token('primary'), caption = th.token('caption'), long = range.value.to - (from ?? range.value.from) > 48 * 3600
  const fmt = (v: number) => (unit === 'W' ? watts(v) : `${num(v, 1)}${NBSP}V`)
  return {
    ...th.base,
    grid: { left: 0, right: 0, top: 8, bottom: 0, containLabel: true },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: th.token('caption') } },
      formatter: (ps: unknown) => {
        const arr = ps as { value: [number, number]; seriesName: string }[]
        const ts = arr[0]!.value[0] / 1000
        const head = long ? `${dayShort(new Date(ts * 1000).toISOString())} ${time(ts)}` : time(ts)
        return [`<b>${head}</b>`, ...arr.map((p) => `${p.seriesName}: ${fmt(p.value[1])}`)].join('<br>')
      } },
    xAxis: { type: 'time', min: (from ?? range.value.from) * 1000, max: range.value.to * 1000, splitLine: { show: false }, axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: caption, fontSize: 11, hideOverlap: true,
        formatter: (v: number) => (long ? dayShort(new Date(v).toISOString()) : time(v / 1000)) } },
    yAxis: { type: 'value', min: min ?? 0, max, scale: unit === 'V', position: 'right', splitNumber: 3, splitLine: th.base.axisCommon.splitLine,
      axisLabel: { color: caption, fontSize: 11, showMinLabel: unit === 'W', formatter: (v: number) => `${num(v)}${NBSP}${unit}` } },
    series: [
      ...(band ? [{ type: 'line' as const, name: t('detail.peak'), data: band.map(([x, y]) => [x * 1000, y]), showSymbol: false,
        lineStyle: { width: 0 }, areaStyle: { color: c, opacity: 0.14 }, z: 1 }] : []),
      { type: 'line', name: unit === 'W' ? t('detail.avgPower') : t('detail.voltageChart'), data: points.map(([x, y]) => [x * 1000, y]),
        showSymbol: false, lineStyle: { width: 1.5, color: c }, z: 2,
        areaStyle: unit === 'W' ? { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: `${c}30` }, { offset: 1, color: `${c}00` }] } } : undefined },
    ],
  }
}
const pts = computed(() => s.data.value?.points ?? [])
// break lines where buckets are missing (tiris not running)
function withGaps<T extends unknown[]>(rows: T[], pick: (r: T) => number, step: number): [number, number][] {
  const out: [number, number][] = []
  rows.forEach((r, i) => {
    const tt = r[0] as number
    if (i && tt - (rows[i - 1]![0] as number) > step * 3) out.push([tt - step, NaN])
    out.push([tt, pick(r)])
  })
  return out
}
// Scale to the 99th percentile of the peaks: one inrush spike (a fridge starts at ~590 W, runs at ~75 W)
// would flatten the whole curve. Clipped peaks stay in the tooltip and are named under the chart.
const yCap = computed(() => {
  const peaks = pts.value.map((p) => p[3]).filter(Number.isFinite).sort((x, y) => x - y)
  if (peaks.length < 20) return { max: undefined, clipped: 0 }
  const p99 = peaks[Math.floor(peaks.length * 0.99)]!
  const max = Math.ceil((p99 * 1.15) / 10) * 10
  return { max, clipped: peaks.filter((v) => v > max).length, top: peaks.at(-1)! }
})
// When the stored data starts late in the range (tiris is new), the chart starts there instead of drawing an empty axis.
const dataFrom = computed(() => {
  const first = pts.value[0]?.[0]
  if (first == null) return null
  const span = range.value.to - range.value.from
  return first - range.value.from > span * 0.2 ? first - (s.data.value?.step_s ?? 60) : null
})
const powerNote = computed(() => [
  dataFrom.value ? t('detail.since', { time: `${dayShort(new Date(dataFrom.value * 1000).toISOString())} ${time(dataFrom.value)}` }) : '',
  yCap.value.clipped ? t('detail.clipped', { max: watts(yCap.value.max), top: watts(yCap.value.top) }) : '',
  d.value?.range.resolution !== 'raw' && d.value?.cycles?.count ? t('detail.cyclesNote') : '',
].filter(Boolean).join(' '))
const powerOption = computed(() => {
  const step = s.data.value?.step_s ?? 60
  return timeLine(withGaps(pts.value, (p) => p[1], step), withGaps(pts.value, (p) => p[3], step), 'W', 0, yCap.value.max, dataFrom.value ?? undefined)
})
const voltOption = computed(() => {
  const step = s.data.value?.step_s ?? 60
  const v = pts.value.filter((p) => p[4] != null)
  // voltage exists only in live measurements (the plug buffer has none): start the axis at the first value
  const from = v.length ? Math.max(range.value.from, v[0]![0] - step) : undefined
  return timeLine(withGaps(v, (p) => p[4]!, step), null, 'V', Math.floor((d.value?.voltage.min ?? 220) - 2), undefined, from)
})
const dailyOption = computed<EChartsOption>(() => {
  const th = theme.value, rows = d.value?.daily ?? []
  return {
    ...th.base,
    grid: { left: 0, right: 0, top: 8, bottom: 0, containLabel: true },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: th.token('muted') } },
      formatter: (ps: unknown) => {
        const p = (ps as { dataIndex: number }[])[0]!, r = rows[p.dataIndex]!
        return `<b>${dayShort(r.day)}</b><br>${kwh(r.wh)}${NBSP}kWh${price.value != null ? `<br>${money(r.wh / 1000 * price.value)}` : ''}`
      } },
    xAxis: { type: 'category', data: rows.map((r) => r.day), axisTick: { show: false }, axisLine: { show: false },
      axisLabel: { color: th.token('caption'), fontSize: 11, formatter: (v: string) => dayShort(v), hideOverlap: true } },
    yAxis: { type: 'value', position: 'right', splitNumber: 3, splitLine: th.base.axisCommon.splitLine,
      axisLabel: { color: th.token('caption'), fontSize: 11, formatter: (v: number) => `${num(v, v < 1 ? 1 : 0)}${NBSP}kWh` } },
    series: [{ type: 'bar', barMaxWidth: 18, emphasis: { itemStyle: { color: th.token('bar-hover') } },
      data: rows.map((r, i) => ({ value: +(r.wh / 1000).toFixed(3), itemStyle: { color: th.token(i === rows.length - 1 ? 'primary' : 'bar'), borderRadius: [2, 2, 0, 0] } })) }],
  }
})
</script>

<template>
  <RouterLink to="/devices" class="mb-2 inline-flex items-center gap-1.5 text-sm text-caption hover:text-foreground">
    <ArrowLeft class="size-4" aria-hidden="true" />{{ t('detail.back') }}
  </RouterLink>
  <div class="mb-7 flex flex-wrap items-end justify-between gap-3">
    <div class="min-w-0">
      <h1 class="text-lg font-semibold">{{ d?.device.name ?? '…' }}</h1>
      <p v-if="d" class="mt-0.5 text-sm text-caption">{{ [d.device.model, d.device.room, d.device.category].filter(Boolean).join(' · ') }}</p>
    </div>
    <Segmented :model-value="hours" :options="hourOptions" :label="t('detail.rangeLabel')" @update:model-value="(v) => setHours(Number(v))" />
  </div>

  <StateMessage v-if="a.isError.value && !d" kind="error" :title="t('states.errorTitle')" :body="t('states.errorBody', { detail: a.error.value?.message ?? '' })"
                :action="t('common.retry')" @action="a.refetch()" />
  <div v-else class="flex flex-col divide-y divide-border transition-opacity" :class="a.isFetching.value && d ? 'opacity-60' : ''">
    <section class="pb-8">
      <div>
        <p class="text-xs font-medium text-caption">{{ t('detail.energy') }}</p>
        <div v-if="!d" class="mt-2 h-12 w-40 animate-pulse rounded-md bg-muted" />
        <p v-else class="mt-2 text-4xl font-semibold tabular">{{ kwh(d.energy_wh) }}<span class="ml-1 text-lg font-medium tracking-normal text-caption">kWh</span></p>
        <p v-if="d && price != null" class="mt-1 text-sm text-muted-foreground tabular">{{ money(d.energy_wh / 1000 * price) }}</p>
      </div>
      <dl v-if="d" class="mt-7 grid grid-cols-2 gap-x-8 gap-y-5 text-sm sm:grid-cols-3 xl:grid-cols-6 xl:gap-0 xl:divide-x xl:divide-border">
        <div class="xl:px-5 xl:first:pl-0"><dt class="text-xs text-caption">{{ t('detail.avgPower') }}</dt>
          <dd class="mt-1 font-semibold tabular">{{ d.power.avg == null ? '–' : watts(d.power.avg) }}</dd>
          <dd v-if="d.power.max != null" class="text-xs text-caption">{{ t('detail.peak') }} {{ watts(d.power.max) }}</dd></div>
        <div class="xl:px-5 xl:first:pl-0"><dt class="text-xs text-caption">{{ t('detail.base') }}</dt>
          <dd class="mt-1 font-semibold tabular">{{ watts(d.power.base) }}</dd>
          <dd class="text-xs text-caption">{{ d.power.base < 0.5 ? t('detail.baseZero') : t('detail.baseSub') }}</dd></div>
        <div class="xl:px-5 xl:first:pl-0"><dt class="text-xs text-caption">{{ t('detail.voltage') }}</dt>
          <dd class="mt-1 font-semibold tabular">{{ d.voltage.avg == null ? '–' : `${num(d.voltage.avg, 1)}${NBSP}V` }}</dd>
          <dd v-if="d.voltage.min != null" class="text-xs text-caption tabular">{{ num(d.voltage.min, 1) }}–{{ num(d.voltage.max, 1) }}{{ NBSP }}V</dd></div>
        <template v-if="d.cycles && d.cycles.count">
          <div class="xl:px-5 xl:first:pl-0"><dt class="text-xs text-caption">{{ t('detail.cycles') }}</dt>
            <dd class="mt-1 font-semibold tabular">{{ num(d.cycles.count) }}</dd>
            <dd class="text-xs text-caption">{{ t('detail.cyclesSub', { n: num(perDay, 1), w: watts(d.cycles.threshold_w) }) }}</dd></div>
          <div class="xl:px-5 xl:first:pl-0"><dt class="text-xs text-caption">{{ t('detail.duty') }}</dt>
            <dd class="mt-1 font-semibold tabular">{{ pct(d.cycles.duty) }}</dd>
            <dd class="text-xs text-caption">{{ t('detail.dutySub') }}</dd></div>
          <div class="xl:pl-5"><dt class="text-xs text-caption">{{ t('detail.runTime') }}</dt>
            <dd class="mt-1 font-semibold tabular">{{ duration(d.cycles.median_s) }}</dd>
            <dd class="text-xs text-caption">{{ t('detail.runTimeSub', { max: duration(d.cycles.max_s) }) }}</dd></div>
        </template>
      </dl>
    </section>

    <Section :title="t('detail.power')" :summary="s.data.value ? t('detail.powerSub', { res: t(`detail.resolution.${s.data.value.bucket}`) }) : undefined">
      <div v-if="!s.data.value" class="h-[260px] animate-pulse rounded-md bg-muted" />
      <p v-else-if="!pts.length" class="py-10 text-center text-sm text-muted-foreground">{{ t('detail.noData') }}</p>
      <EChart v-else :option="powerOption" :height="260" :label="t('detail.power')" />
      <p v-if="powerNote" class="mt-3 text-sm text-caption">{{ powerNote }}</p>
    </Section>

    <div class="grid gap-x-12 lg:grid-cols-2">
      <Section :title="t('detail.voltageChart')" :summary="t('detail.voltageSub2')">
        <div v-if="!s.data.value" class="h-[200px] animate-pulse rounded-md bg-muted" />
        <p v-else-if="!pts.length" class="py-10 text-center text-sm text-muted-foreground">{{ t('detail.noData') }}</p>
        <EChart v-else :option="voltOption" :height="200" :label="t('detail.voltageChart')" />
      </Section>
      <Section :title="t('detail.daily')" :summary="t('detail.dailySub')" class="border-t border-border lg:border-t-0">
        <div v-if="!d" class="h-[200px] animate-pulse rounded-md bg-muted" />
        <EChart v-else :option="dailyOption" :height="200" :label="t('detail.daily')" />
      </Section>
    </div>
  </div>
</template>
