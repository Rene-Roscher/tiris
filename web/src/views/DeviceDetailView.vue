<script setup lang="ts">
import { ArrowLeft } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import EChart from '@/components/charts/EChart.vue'
import KpiTile from '@/components/KpiTile.vue'
import PageHeader from '@/components/PageHeader.vue'
import Panel from '@/components/Panel.vue'
import StateMessage from '@/components/StateMessage.vue'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
  const th = theme.value, c = th.token('chart-1'), long = range.value.to - (from ?? range.value.from) > 48 * 3600
  const fmt = (v: number) => (unit === 'W' ? watts(v) : `${num(v, 1)}${NBSP}V`)
  return {
    ...th.base,
    grid: { left: 8, right: 16, top: 28, bottom: 4, containLabel: true },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: th.token('caption') } },
      formatter: (ps: unknown) => {
        const arr = ps as { value: [number, number]; seriesName: string }[]
        const ts = arr[0]!.value[0] / 1000
        const head = long ? `${dayShort(new Date(ts * 1000).toISOString())} ${time(ts)}` : time(ts)
        return [`<b>${head}</b>`, ...arr.map((p) => `${p.seriesName}: ${fmt(p.value[1])}`)].join('<br>')
      } },
    xAxis: { type: 'time', min: (from ?? range.value.from) * 1000, max: range.value.to * 1000, splitLine: { show: false }, axisLine: th.base.axisCommon.axisLine,
      axisLabel: { ...th.base.axisCommon.axisLabel, hideOverlap: true,
        formatter: (v: number) => (long ? dayShort(new Date(v).toISOString()) : time(v / 1000)) } },
    yAxis: { type: 'value', min: min ?? 0, max, scale: unit === 'V', splitLine: th.base.axisCommon.splitLine, name: unit, nameGap: 12,
      nameTextStyle: { color: th.token('caption'), align: 'left' },
      axisLabel: { ...th.base.axisCommon.axisLabel, formatter: (v: number) => num(v) } },
    series: [
      ...(band ? [{ type: 'line' as const, name: t('detail.peak'), data: band.map(([x, y]) => [x * 1000, y]), showSymbol: false,
        lineStyle: { width: 0 }, areaStyle: { color: c, opacity: 0.14 }, z: 1 }] : []),
      { type: 'line', name: unit === 'W' ? t('detail.avgPower') : t('detail.voltageChart'), data: points.map(([x, y]) => [x * 1000, y]),
        showSymbol: false, lineStyle: { width: 2, color: c }, areaStyle: unit === 'W' ? { color: c, opacity: 0.08 } : undefined, z: 2 },
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
const powerOption = computed(() => {
  const step = s.data.value?.step_s ?? 60
  return timeLine(withGaps(pts.value, (p) => p[1], step), withGaps(pts.value, (p) => p[3], step), 'W', 0, yCap.value.max)
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
    grid: { ...th.base.grid, top: 28 },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: th.token('muted') } },
      formatter: (ps: unknown) => {
        const p = (ps as { dataIndex: number }[])[0]!, r = rows[p.dataIndex]!
        return `<b>${dayShort(r.day)}</b><br>${kwh(r.wh)}${NBSP}kWh${price.value != null ? `<br>${money(r.wh / 1000 * price.value)}` : ''}`
      } },
    xAxis: { type: 'category', data: rows.map((r) => r.day), axisTick: { show: false }, axisLine: th.base.axisCommon.axisLine,
      axisLabel: { ...th.base.axisCommon.axisLabel, formatter: (v: string) => dayShort(v), hideOverlap: true } },
    yAxis: { type: 'value', splitLine: th.base.axisCommon.splitLine, name: 'kWh', nameGap: 12, nameTextStyle: { color: th.token('caption'), align: 'left' },
      axisLabel: { ...th.base.axisCommon.axisLabel, formatter: (v: number) => num(v, v < 1 ? 1 : 0) } },
    series: [{ type: 'bar', barMaxWidth: 18, itemStyle: { color: th.token('chart-1'), borderRadius: [3, 3, 0, 0] },
      data: rows.map((r) => +(r.wh / 1000).toFixed(3)) }],
  }
})
</script>

<template>
  <RouterLink to="/devices" class="mb-3 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
    <ArrowLeft class="size-4" aria-hidden="true" />{{ t('detail.back') }}
  </RouterLink>
  <PageHeader :title="d?.device.name ?? '…'" :description="d ? [d.device.model, d.device.room, d.device.category].filter(Boolean).join(', ') : undefined">
    <Tabs :model-value="String(hours)" @update:model-value="(v) => setHours(Number(v))">
      <TabsList>
        <TabsTrigger value="24">{{ t('detail.range.h24') }}</TabsTrigger>
        <TabsTrigger value="168">{{ t('detail.range.d7') }}</TabsTrigger>
        <TabsTrigger value="720">{{ t('detail.range.d30') }}</TabsTrigger>
      </TabsList>
    </Tabs>
  </PageHeader>

  <StateMessage v-if="a.isError.value && !d" kind="error" :title="t('states.errorTitle')" :body="t('states.errorBody', { detail: a.error.value?.message ?? '' })"
                :action="t('common.retry')" @action="a.refetch()" />
  <div v-else class="flex flex-col gap-4 transition-opacity duration-200" :class="a.isFetching.value && d ? 'opacity-60' : ''">
    <section class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiTile :label="t('detail.energy')" :value="kwh(d?.energy_wh)" unit="kWh" :loading="!d"
               :sub="price != null && d ? money(d.energy_wh / 1000 * price) : undefined" />
      <KpiTile :label="t('detail.avgPower')" :value="d?.power.avg == null ? '–' : num(d.power.avg, d.power.avg < 10 ? 1 : 0)" unit="W" :loading="!d"
               :sub="d?.power.max != null ? `${t('detail.peak')} ${watts(d.power.max)}` : undefined" />
      <KpiTile :label="t('detail.base')" :value="d ? num(d.power.base, d.power.base < 10 ? 1 : 0) : '–'" unit="W" :loading="!d" :sub="t('detail.baseSub')" />
      <KpiTile :label="t('detail.voltage')" :value="d?.voltage.avg == null ? '–' : num(d.voltage.avg, 1)" unit="V" :loading="!d"
               :sub="d?.voltage.min != null ? t('detail.voltageSub', { min: `${num(d.voltage.min, 1)}${NBSP}V`, max: `${num(d.voltage.max, 1)}${NBSP}V` }) : undefined" />
      <template v-if="d?.cycles && d.cycles.count">
        <KpiTile :label="t('detail.cycles')" :value="num(d.cycles.count)" :sub="t('detail.cyclesSub', { n: num(perDay, 1), w: watts(d.cycles.threshold_w) })" />
        <KpiTile :label="t('detail.duty')" :value="pct(d.cycles.duty)" :sub="t('detail.dutySub')" />
        <KpiTile :label="t('detail.runTime')" :value="duration(d.cycles.median_s)" :sub="t('detail.runTimeSub', { max: duration(d.cycles.max_s) })" />
      </template>
    </section>
    <p v-if="d?.range.resolution !== 'raw' && d?.cycles?.count" class="-mt-2 text-sm text-caption">{{ t('detail.cyclesNote') }}</p>

    <Panel :title="t('detail.power')" :description="s.data.value ? t('detail.powerSub', { res: t(`detail.resolution.${s.data.value.bucket}`) }) : undefined">
      <div v-if="!s.data.value" class="h-[280px] animate-pulse rounded-md bg-muted" />
      <p v-else-if="!pts.length" class="py-10 text-center text-sm text-muted-foreground">{{ t('detail.noData') }}</p>
      <EChart v-else :option="powerOption" :height="280" :label="t('detail.power')" />
      <p v-if="yCap.clipped" class="mt-2 text-sm text-caption">{{ t('detail.clipped', { max: watts(yCap.max), top: watts(yCap.top) }) }}</p>
    </Panel>

    <section class="grid gap-4 lg:grid-cols-2">
      <Panel :title="t('detail.voltageChart')" :description="t('detail.voltageSub2')">
        <div v-if="!s.data.value" class="h-[220px] animate-pulse rounded-md bg-muted" />
        <p v-else-if="!pts.length" class="py-10 text-center text-sm text-muted-foreground">{{ t('detail.noData') }}</p>
        <EChart v-else :option="voltOption" :height="220" :label="t('detail.voltageChart')" />
      </Panel>
      <Panel :title="t('detail.daily')" :description="t('detail.dailySub')">
        <div v-if="!d" class="h-[220px] animate-pulse rounded-md bg-muted" />
        <EChart v-else :option="dailyOption" :height="220" :label="t('detail.daily')" />
      </Panel>
    </section>
  </div>
</template>
