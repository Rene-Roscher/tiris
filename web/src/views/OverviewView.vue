<script setup lang="ts">
/*
  Overview (Linear-calm): a hero row with the three answers (now, month so far, where the month lands),
  then sections separated by hairlines. Charts in one neutral tone; only today is in the accent.
*/
import { useQuery } from '@tanstack/vue-query'
import type { EChartsOption } from 'echarts'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import EChart from '@/components/charts/EChart.vue'
import LiveSpark from '@/components/charts/LiveSpark.vue'
import Sparkline from '@/components/charts/Sparkline.vue'
import Section from '@/components/Section.vue'
import RunTimeline from '@/components/RunTimeline.vue'
import Segmented from '@/components/Segmented.vue'
import StateMessage from '@/components/StateMessage.vue'
import { useChartTheme } from '@/composables/useChartTheme'
import { useLive } from '@/composables/useLive'
import { useToday } from '@/composables/useToday'
import { useTween } from '@/composables/useTween'
import { ApiError, api } from '@/lib/api'
import { animated, mix } from '@/lib/charts'
import { slotVar } from '@/lib/colors'
import { dayLong, dayShort, eurFromWh, kwh, money, monthLong, monthShort, monthYear, NBSP, num, pct, time, watts } from '@/lib/format'
import type { Device, Overview, SeriesResponse } from '@/lib/types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const theme = useChartTheme()
const live = useLive()

type Range = 7 | 30 | 90 | 'all'
const RANGES: Range[] = [7, 30, 90, 'all']
const days = computed<Range>({
  get: () => { const v = route.query.days === 'all' ? 'all' : Number(route.query.days); return RANGES.includes(v as Range) ? (v as Range) : 30 },
  set: (v) => router.replace({ query: { ...route.query, days: v === 30 ? undefined : String(v) } }),
})
const isAll = computed(() => days.value === 'all')
const rangeOptions = computed(() => [
  { value: 7 as Range, label: t('overview.range.d7') }, { value: 30 as Range, label: t('overview.range.d30') },
  { value: 90 as Range, label: t('overview.range.d90') }, { value: 'all' as Range, label: t('overview.range.all') },
])

const q = useQuery({
  queryKey: computed(() => ['overview', days.value, null]),
  queryFn: () => api.get<Overview>(days.value === 'all' ? '/api/overview?all=true' : `/api/overview?days=${days.value}`),
  placeholderData: (prev) => prev,
  refetchInterval: 5 * 60_000,
})
const devs = useQuery({ queryKey: ['devices'], queryFn: () => api.get<{ devices: Device[] }>('/api/devices'), staleTime: 30_000 })
const health = useQuery({ queryKey: ['health'], queryFn: () => api.get<{ tapo: boolean }>('/api/health'), staleTime: 60_000 })
const d = computed(() => q.data.value)
// 503 = no data yet (or no Tapo account): an empty state, not an error
const empty = computed(() => q.error.value instanceof ApiError && q.error.value.status === 503)
const k = computed(() => d.value?.kpi)
const price = computed(() => d.value?.price ?? null)
const meta = computed(() => Object.fromEntries((devs.data.value?.devices ?? []).map((x) => [x.id, x])))
const names = computed(() => Object.fromEntries((d.value?.devices ?? []).map((x) => [x.id, x.name])))
const slots = computed(() => Object.fromEntries((d.value?.devices ?? []).map((x) => [x.id, x.slot])))
const tokenOf = (key: string) => (key === 'other' ? 'chart-other' : `chart-${slots.value[key] || 'other'}`)

/* series: the coloured devices plus "other"; the legend toggles them in every chart of this view */
const seriesKeys = computed(() => (d.value?.series_keys ?? []).map((key) => ({
  key, label: key === 'other' ? t('overview.other') : names.value[key] ?? key, css: key === 'other' ? slotVar(0) : slotVar(slots.value[key]),
})))
const hidden = ref<Set<string>>(new Set())
// pointing at a legend entry highlights that device in every chart of the view
type ChartRef = { highlight: (n: string) => void; downplay: (n: string) => void } | null
const todayChart = ref<ChartRef>(null), dailyChart = ref<ChartRef>(null), monthsChart = ref<ChartRef>(null), allChart = ref<ChartRef>(null)
const point = (label: string, on: boolean) => {
  for (const c of [todayChart.value, dailyChart.value, monthsChart.value, allChart.value]) (on ? c?.highlight : c?.downplay)?.(label)
}
const runDay = ref<'today' | 'yesterday'>('today')
const today = useToday()   // rolls over at midnight when the page stays open
const runDayIso = computed(() => { const x = new Date(`${today.value}T12:00`); if (runDay.value === 'yesterday') x.setDate(x.getDate() - 1); return x.toLocaleDateString('sv-SE') })
const runDayOptions = computed(() => [{ value: 'today' as const, label: t('common.today') }, { value: 'yesterday' as const, label: t('common.yesterday') }])
function toggle(key: string) {
  const h = new Set(hidden.value)
  if (h.has(key)) h.delete(key)
  else if (h.size < seriesKeys.value.length - 1) h.add(key)
  hidden.value = h
}
const legendSelected = computed(() => Object.fromEntries(seriesKeys.value.map((s) => [s.label, !hidden.value.has(s.key)])))
const ratio = (a?: number | null, b?: number | null) => (a == null || !b ? null : a / b - 1)

const month = computed(() => new Intl.DateTimeFormat(undefined, { month: 'long' }).format(d.value ? new Date(d.value.now) : new Date()))
const prevMonth = computed(() => {
  const n = d.value ? new Date(d.value.now) : new Date()
  return new Intl.DateTimeFormat(undefined, { month: 'long' }).format(new Date(n.getFullYear(), n.getMonth() - 1, 1))
})
const monthDelta = computed(() => ratio(k.value?.mtd_complete_wh, k.value?.prev_month_same_wh))
const monthProgress = computed(() => (k.value?.forecast_month_wh ? Math.min(1, k.value.mtd_wh / k.value.forecast_month_wh) : 0))

const nowW = computed(() => live.snapshot.value?.total_w ?? null)
const nowTween = useTween(nowW)
const liveW = (id: string) => live.snapshot.value?.devices[id]?.w ?? null

/* daily: one tone, today in the accent, average dashed; the tooltip names the devices */
const dailyOption = computed<EChartsOption>(() => {
  const th = theme.value, rows = d.value?.daily ?? [], last = rows.length - 1
  const done = rows.slice(0, -1), avg = done.reduce((s, r) => s + r.total, 0) / Math.max(1, done.length) / 1000
  const caption = th.token('caption'), keys = seriesKeys.value
  return {
    ...th.base,
    ...animated(),
    legend: { show: false, selected: legendSelected.value },
    grid: { left: 0, right: 0, top: 8, bottom: 0, containLabel: true },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: th.token('muted') } },
      formatter: (ps: unknown) => {
        const i = (ps as { dataIndex: number }[])[0]!.dataIndex, r = rows[i]!
        const parts = keys.filter((k) => !hidden.value.has(k.key) && (r.by[k.key] ?? 0) > 0).sort((a, b) => (r.by[b.key] ?? 0) - (r.by[a.key] ?? 0))
        const sum = parts.reduce((s, k) => s + (r.by[k.key] ?? 0), 0)
        const line = (dot: string, a: string, b: string) => `<div style="display:flex;justify-content:space-between;gap:16px"><span>${dot}${a}</span><b style="font-weight:500">${b}</b></div>`
        const dot = (k: string) => `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px;background:${th.token(tokenOf(k))}"></span>`
        return `<div style="min-width:200px"><div style="display:flex;justify-content:space-between;gap:16px;margin-bottom:4px;font-weight:600"><span>${dayLong(r.day)}${i === last ? ` (${t('overview.soFar')})` : ''}</span><span>${kwh(sum, 2)}${NBSP}kWh</span></div>` +
          parts.map((k) => line(dot(k.key), k.label, kwh(r.by[k.key] ?? 0, 2))).join('') +
          (price.value != null ? `<div style="margin-top:4px">${line('', t('overview.cost'), eurFromWh(sum, price.value))}</div>` : '') + '</div>'
      } },
    xAxis: { type: 'category', data: rows.map((r) => r.day), axisTick: { show: false }, axisLine: { show: false },
      axisLabel: { color: caption, fontSize: 11, hideOverlap: true, formatter: (v: string, i: number) => (i === last ? t('overview.todayShort') : dayShort(v)) } },
    yAxis: { type: 'value', position: 'right', splitNumber: 3, splitLine: th.base.axisCommon.splitLine,
      axisLabel: { color: caption, fontSize: 11, formatter: (v: number) => `${num(v)}${NBSP}kWh` } },
    series: keys.map((k, si) => ({
      type: 'bar' as const, name: k.label, stack: 'day', barMaxWidth: 22, barCategoryGap: '34%',
      itemStyle: { color: th.token(tokenOf(k.key)), borderColor: th.token('background'), borderWidth: rows.length > 60 ? 0 : 1 },
      emphasis: { focus: 'series' as const },
      data: rows.map((r, i) => ({ value: +((r.by[k.key] ?? 0) / 1000).toFixed(3), itemStyle: { opacity: i === last ? 0.55 : 1 } })),
      ...(si === 0 ? { markLine: { silent: true, symbol: 'none', lineStyle: { color: caption, type: [3, 3] as number[], width: 1 },
        label: { position: 'insideEndTop' as const, color: th.token('muted-foreground'), fontSize: 11, formatter: `Ø ${num(avg, 1)}` },
        data: [{ yAxis: +avg.toFixed(2) }] } } : {}),
    })),
  }
})
const dailySummary = computed(() => {
  if (!k.value || !d.value) return ''
  if (d.value.range.all) {
    const p = [t('overview.sinceLine', { since: monthYear(d.value.range.start), kwh: kwh(k.value.range_wh, 0),
      eur: price.value != null ? `, ≈ ${money(k.value.range_wh / 1000 * price.value, 0)}` : '' })]
    if (k.value.peak_month) p.push(t('overview.peakMonth', { month: monthLong(k.value.peak_month.month), value: kwh(k.value.peak_month.wh, 0) }))
    return p.join(' · ')
  }
  const parts = [`${kwh(k.value.range_wh, 0)}${NBSP}kWh`]
  if (price.value != null) parts[0] += `, ${eurFromWh(k.value.range_wh, price.value)}`
  if (k.value.peak_day) parts.push(t('overview.peak', { day: dayLong(k.value.peak_day.day), value: kwh(k.value.peak_day.total) }))
  return parts.join(' · ')
})

/* today: quarter hours per device (stacked), yesterday's total dashed for comparison */
const midnight = (offset = 0) => { const x = new Date(); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() + offset); return x }
const todayQ = useQuery({
  queryKey: computed(() => ['today-split', today.value]),
  queryFn: async () => {
    const t0 = midnight(), y0 = midnight(-1)
    const enc = (x: Date) => encodeURIComponent(x.toISOString())
    const [today, yest] = await Promise.all([
      api.get<{ step_s: number; series: Record<string, [number, number, number, number, number | null, number, number][]> }>(`/api/series?from=${enc(t0)}&bucket=15m&split=true`),
      api.get<SeriesResponse>(`/api/series?from=${enc(y0)}&to=${enc(t0)}&bucket=15m`),
    ])
    return { t0: t0.getTime() / 1000, today, yest }
  },
  refetchInterval: 60_000,
})
const todayOption = computed<EChartsOption>(() => {
  const th = theme.value, data = todayQ.data.value, caption = th.token('caption')
  if (!data) return {}
  const t0 = data.t0, keys = seriesKeys.value.map((k) => k.key)
  const times = [...new Set(Object.values(data.today.series).flat().map((p) => p[0]))].sort((a, b) => a - b)
  const per = (key: string) => {
    const ids = key === 'other' ? Object.keys(data.today.series).filter((id) => !keys.includes(id)) : [key]
    return times.map((tt) => [tt * 1000, +ids.reduce((s, id) => s + (data.today.series[id]?.find((p) => p[0] === tt)?.[1] ?? 0), 0).toFixed(1)])
  }
  const yest = (data.yest.points ?? []).map((p) => [(p[0] + 86400) * 1000, p[1]])
  return {
    ...th.base,
    ...animated(),
    legend: { show: false, selected: { ...legendSelected.value, [t('overview.yesterday')]: true } },
    grid: { left: 0, right: 0, top: 8, bottom: 0, containLabel: true },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: caption } },
      formatter: (ps: unknown) => {
        const arr = (ps as { value: [number, number]; seriesName: string; color: string }[]).filter((p) => p.value[1] > 0.05)
        if (!arr.length) return ''
        const head = time(arr[0]!.value[0] / 1000)
        return `<b>${head}</b><br>` + arr.map((p) => `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px;background:${p.color}"></span>${p.seriesName}: ${watts(p.value[1])}`).join('<br>')
      } },
    xAxis: { type: 'time', min: t0 * 1000, max: (t0 + 86400) * 1000, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { color: caption, fontSize: 11, formatter: (v: number) => time(v / 1000) } },
    yAxis: { type: 'value', position: 'right', splitNumber: 3, splitLine: th.base.axisCommon.splitLine,
      axisLabel: { color: caption, fontSize: 11, formatter: (v: number) => `${num(v)}${NBSP}W` } },
    series: [
      ...seriesKeys.value.map((k) => ({
        type: 'line' as const, name: k.label, stack: 'w', step: 'end' as const, showSymbol: false, data: per(k.key),
        lineStyle: { width: 0 }, areaStyle: { color: th.token(tokenOf(k.key)), opacity: 0.9 }, emphasis: { focus: 'series' as const },
      })),
      { type: 'line' as const, name: t('overview.yesterday'), data: yest, step: 'end' as const, showSymbol: false, z: 5,
        lineStyle: { color: th.token('muted-foreground'), width: 1, type: [3, 3] as number[] } },
    ],
  }
})
const todaySummary = computed(() => {
  const data = todayQ.data.value
  if (!data) return ''
  const wh = Object.values(data.today.series).flat().reduce((s, p) => s + (p[5] ?? 0), 0)
  const cut = Date.now() / 1000 - 86400
  const ywh = (data.yest.points ?? []).filter((p) => p[0] < cut).reduce((s, p) => s + (p[5] ?? 0), 0)
  return t('overview.todayLine', { kwh: kwh(wh, 2), eur: price.value != null ? `, ${eurFromWh(wh, price.value)}` : '', y: kwh(ywh, 2) })
})

/* months: stacked by device like the daily chart; the running month lighter, its forecast outlined */
const monthsOption = computed<EChartsOption>(() => {
  const th = theme.value, ms = d.value?.months ?? [], fc = k.value?.forecast_month_wh ?? 0, caption = th.token('caption'), keys = seriesKeys.value
  const dot = (k: string) => `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px;background:${th.token(tokenOf(k))}"></span>`
  return {
    ...th.base,
    ...animated(),
    legend: { show: false, selected: legendSelected.value },
    grid: { left: 0, right: 0, top: 8, bottom: 0, containLabel: true },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: th.token('muted') } },
      formatter: (ps: unknown) => {
        const m = ms[(ps as { dataIndex: number }[])[0]!.dataIndex]!
        const parts = keys.filter((k) => !hidden.value.has(k.key) && (m.by?.[k.key] ?? 0) > 0).sort((a, b) => (m.by?.[b.key] ?? 0) - (m.by?.[a.key] ?? 0))
        const sum = parts.reduce((s, k) => s + (m.by?.[k.key] ?? 0), 0)
        const line = (a: string, b: string) => `<div style="display:flex;justify-content:space-between;gap:16px"><span>${a}</span><b style="font-weight:500">${b}</b></div>`
        return `<div style="min-width:200px"><div style="display:flex;justify-content:space-between;gap:16px;margin-bottom:4px;font-weight:600"><span>${monthLong(m.month)}${m.partial ? ` (${t('overview.soFar')})` : ''}</span><span>${kwh(sum, 0)}${NBSP}kWh</span></div>` +
          parts.map((k) => line(dot(k.key) + k.label, kwh(m.by?.[k.key] ?? 0, 1))).join('') +
          (price.value != null ? `<div style="margin-top:4px">${line(t('overview.cost'), eurFromWh(sum, price.value))}</div>` : '') +
          (m.partial && fc ? `<div style="margin-top:4px">${line(t('overview.forecast'), `${kwh(fc, 0)}${NBSP}kWh`)}</div>` : '') + '</div>'
      } },
    xAxis: { type: 'category', data: ms.map((m) => m.month), axisTick: { show: false }, axisLine: { show: false },
      axisLabel: { color: caption, fontSize: 11, hideOverlap: true, formatter: (v: string) => (ms.length > 14 ? monthYear(v) : monthShort(v)) } },
    yAxis: { type: 'value', position: 'right', splitNumber: 3, splitLine: th.base.axisCommon.splitLine, axisLabel: { color: caption, fontSize: 11, formatter: (v: number) => `${num(v)}${NBSP}kWh` } },
    series: [
      { type: 'bar', name: '_forecast', barGap: '-100%', barMaxWidth: 26, silent: true, z: 1, stack: undefined,
        itemStyle: { color: 'transparent', borderColor: th.token('border-strong'), borderWidth: 1, borderType: [3, 2], borderRadius: [2, 2, 0, 0] },
        data: ms.map((m) => (m.partial && fc > m.wh ? +(fc / 1000).toFixed(1) : null)) },
      ...keys.map((k) => ({
        type: 'bar' as const, name: k.label, stack: 'm', barMaxWidth: 26, z: 2, emphasis: { focus: 'series' as const },
        itemStyle: { color: th.token(tokenOf(k.key)), borderColor: th.token('background'), borderWidth: 1 },
        data: ms.map((m) => ({ value: +((m.by?.[k.key] ?? 0) / 1000).toFixed(2), itemStyle: { opacity: m.partial ? 0.55 : 1 } })),
      })),
    ],
  }
})
const monthsSummary = computed(() => {
  const full = (d.value?.months ?? []).filter((m) => !m.partial).slice(-12)
  if (!full.length) return ''
  const sum = full.reduce((s, m) => s + m.wh, 0)
  return t('overview.last12', { kwh: kwh(sum, 0), eur: price.value != null ? `, ${money(sum / 1000 * price.value, 0)}` : '' })
})

/* when: one hue from the empty surface to the accent, scaled to the 95th percentile */
const heatOption = computed<EChartsOption>(() => {
  const th = theme.value, cells = d.value?.heat ?? []
  const dows = new Intl.DateTimeFormat(undefined, { weekday: 'short' })
  const dayNames = [1, 2, 3, 4, 5, 6, 7].map((i) => dows.format(new Date(2024, 0, i)))   // 2024-01-01 is a Monday
  const sorted = cells.map((c) => c.wh).sort((a, b) => a - b)
  const max = Math.max(1, sorted[Math.floor(sorted.length * 0.95)] ?? 1)
  const from = th.token('heat-0'), to = th.token('primary'), caption = th.token('caption')
  return {
    ...th.base,
    grid: { left: 0, right: 0, top: 0, bottom: 24, containLabel: true },
    tooltip: { ...th.base.tooltip, formatter: (p: unknown) => {
      const v = (p as { value: [number, number, number] }).value
      return `<b>${dayNames[v[1]]} ${String(v[0]).padStart(2, '0')}–${String(v[0] + 1).padStart(2, '0')}</b><br>Ø ${num(v[2])}${NBSP}Wh`
    } },
    xAxis: { type: 'category', data: Array.from({ length: 24 }, (_, i) => i), axisTick: { show: false }, axisLine: { show: false },
      axisLabel: { color: caption, fontSize: 11, interval: 5 } },
    yAxis: { type: 'category', data: dayNames, inverse: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: caption, fontSize: 11 } },
    visualMap: { show: false, dimension: 2, min: 0, max, inRange: { color: [0, 0.25, 0.5, 0.75, 1].map((s) => mix(from, to, s * 0.85)) } },
    series: [{ type: 'heatmap', itemStyle: { borderColor: th.token('background'), borderWidth: 2, borderRadius: 2 },
      data: cells.map((c) => [c.hour, c.dow - 1, Math.round(c.wh)]) }],   // wh is already the average per hour
  }
})

/* devices: sorted by what draws now, then by energy in the range */
const rows = computed(() => {
  const list = d.value?.devices ?? []
  const total = list.reduce((s, x) => s + x.range_wh, 0)
  const maxW = Math.max(1, ...list.map((x) => liveW(x.id) ?? 0))
  return [...list]
    .map((x) => {
      const w = liveW(x.id), m = meta.value[x.id]
      return { ...x, w, css: slotVar(x.slot), on: m?.status?.device_on !== false, room: m?.room ?? null, share: total ? x.range_wh / total : 0, bar: (w ?? 0) / maxW }
    })
    .sort((a, b) => Number(b.on) - Number(a.on) || (b.w ?? -1) - (a.w ?? -1) || b.range_wh - a.range_wh)
})
const shares = computed(() => {
  const list = d.value?.devices ?? [], total = list.reduce((s, x) => s + x.range_wh, 0)
  if (!total) return []
  const colored = list.filter((x) => x.slot).map((x) => ({ key: x.id, label: x.name, css: slotVar(x.slot), wh: x.range_wh }))
  const rest = list.filter((x) => !x.slot).reduce((s, x) => s + x.range_wh, 0)
  return [...colored, ...(rest > 0 ? [{ key: 'other', label: t('overview.other'), css: slotVar(0), wh: rest }] : [])]
    .map((x) => ({ ...x, share: x.wh / total })).filter((x) => x.share >= 0.005)
})
const totals = computed(() => ({
  w: nowW.value, today: k.value?.today_wh ?? 0, range: rows.value.reduce((s, x) => s + x.range_wh, 0),
}))
const open = (id: string) => router.push(`/devices/${id}`)
</script>

<template>
  <div class="mb-7 flex h-9 items-center justify-between gap-3">
    <h1 class="font-semibold">{{ t('overview.title') }}</h1>
    <Segmented v-if="!empty" v-model="days" :options="rangeOptions" :label="t('overview.rangeLabel')" />
  </div>

  <StateMessage v-if="empty && health.data.value?.tapo === false" kind="setup" :title="t('states.noTapoTitle')" :body="t('states.noTapoBody')" />
  <StateMessage v-else-if="empty" :title="t('states.noDataTitle')" :body="t('states.noDataBody')" />
  <StateMessage v-else-if="q.isError.value && !d" kind="error" :title="t('states.errorTitle')"
                :body="t('states.errorBody', { detail: String(q.error.value?.message ?? '') })" :action="t('common.retry')"
                :busy="q.isFetching.value" @action="q.refetch()" />
  <StateMessage v-else-if="q.isSuccess.value && !d?.devices.length" :title="t('states.noDataTitle')" :body="t('states.noDataBody')" />

  <div v-else class="flex flex-col divide-y divide-border">
    <!-- hero: the only big numbers on the page -->
    <section class="grid gap-6 pb-8 lg:grid-cols-[1.25fr_1fr_1fr] lg:gap-0 lg:divide-x lg:divide-border">
      <div class="min-w-0 lg:pr-8">
        <p class="text-xs font-medium text-caption">{{ t('overview.now') }}</p>
        <p class="mt-2 text-4xl font-semibold tabular">
          {{ nowTween == null ? '–' : num(nowTween, nowTween < 100 ? 1 : 0) }}<span class="ml-1 text-lg font-medium tracking-normal text-caption">W</span>
        </p>
        <LiveSpark class="mb-2.5 mt-3.5" :points="live.total.value.slice(-300)" />
        <p v-if="nowW != null && price != null" class="text-sm text-muted-foreground">{{ t('overview.atThisLoad', { value: money(nowW * 24 / 1000 * price) }) }}</p>
        <p v-if="k?.base_w != null" class="text-sm text-caption">
          {{ price != null ? t('overview.baseLoadLine', { w: num(k.base_w), eur: money(k.base_w * 8.76 * price, 0) }) : t('overview.baseLoadLineKwh', { w: num(k.base_w), kwh: num(k.base_w * 8.76) }) }}
        </p>
      </div>

      <div class="min-w-0 border-t border-border pt-6 lg:border-t-0 lg:px-8 lg:pt-0">
        <p class="text-xs font-medium text-caption">{{ t('overview.monthSoFar', { month }) }}</p>
        <div v-if="!k" class="mt-2 h-8 w-32 animate-pulse rounded-md bg-muted" />
        <template v-else>
          <p class="mt-2 text-2xl font-semibold tabular">{{ kwh(k.mtd_wh, 1) }}<span class="ml-1 text-base font-medium tracking-normal text-caption">kWh</span></p>
          <p v-if="price != null" class="mt-1 text-sm text-muted-foreground tabular">{{ eurFromWh(k.mtd_wh, price) }}</p>
          <RouterLink v-else to="/costs" class="mt-1 inline-block text-sm text-link hover:underline">{{ t('overview.tariffHint') }}</RouterLink>
          <p v-if="monthDelta != null" class="mt-2 text-sm text-muted-foreground">
            <span class="font-medium tabular" :class="monthDelta > 0 ? 'text-bad' : 'text-good'">{{ (monthDelta > 0 ? '+' : '') + pct(monthDelta) }}</span>
            {{ t('overview.vsMonthSameTime', { month: prevMonth }) }}
          </p>
        </template>
      </div>

      <div class="min-w-0 border-t border-border pt-6 lg:border-t-0 lg:pl-8 lg:pt-0">
        <p class="text-xs font-medium text-caption">{{ t('overview.forecastOf', { month }) }}</p>
        <div v-if="!k" class="mt-2 h-8 w-32 animate-pulse rounded-md bg-muted" />
        <template v-else>
          <p class="mt-2 text-2xl font-semibold tabular">
            {{ kwh(k.forecast_month_wh, 0) }}<span class="ml-1 text-base font-medium tracking-normal text-caption">kWh</span>
            <span v-if="price != null" class="ml-1.5 text-lg font-medium tracking-normal text-muted-foreground">{{ eurFromWh(k.forecast_month_wh, price) }}</span>
          </p>
          <div class="mb-2.5 mt-4 h-1 overflow-hidden rounded-full bg-border-strong" role="meter" :aria-valuenow="Math.round(monthProgress * 100)"
               aria-valuemin="0" aria-valuemax="100" :aria-label="t('overview.forecastOf', { month })">
            <div class="h-full origin-left rounded-full bg-primary" :style="{ transform: `scaleX(${monthProgress.toFixed(3)})` }" />
          </div>
          <p class="text-sm text-muted-foreground tabular">
            {{ t('overview.yearLine', { kwh: kwh(k.forecast_year_wh, 0), eur: price != null ? `, ${money(k.forecast_year_wh / 1000 * price, 0)}` : '' }) }}
          </p>
        </template>
      </div>
    </section>

    <Section :title="t('overview.today')" :summary="todaySummary">
      <ul class="mb-4 flex flex-wrap gap-1" :aria-label="t('overview.legend')">
        <li v-for="k in seriesKeys" :key="k.key">
          <button type="button" class="flex h-7 items-center gap-2 rounded-md px-2 text-sm transition-[color,background-color,opacity] hover:bg-muted"
                  :class="hidden.has(k.key) ? 'text-caption opacity-60' : 'text-muted-foreground'" :aria-pressed="!hidden.has(k.key)" @click="toggle(k.key)"
                  @mouseenter="point(k.label, true)" @mouseleave="point(k.label, false)" @focus="point(k.label, true)" @blur="point(k.label, false)">
            <span class="size-2.5 rounded-sm" :style="{ background: hidden.has(k.key) ? 'var(--border-strong)' : k.css }" aria-hidden="true" />{{ k.label }}
          </button>
        </li>
        <li class="ml-1 flex h-7 items-center gap-2 px-2 text-sm text-caption">
          <span class="w-3 border-t border-dashed border-muted-foreground" aria-hidden="true" />{{ t('overview.yesterday') }}
        </li>
      </ul>
      <div v-if="!todayQ.data.value" class="h-[200px] animate-pulse rounded-md bg-muted" />
      <EChart v-else ref="todayChart" :option="todayOption" :height="200" :label="t('overview.today')" />
    </Section>

    <Section :title="t('events.title')">
      <template #actions><Segmented v-model="runDay" :options="runDayOptions" :label="t('events.dayLabel')" /></template>
      <RunTimeline :day="runDayIso" />
    </Section>

    <Section :title="isAll ? t('overview.allMonths') : t('overview.daily')" :summary="dailySummary">
      <div v-if="!d" class="h-[240px] animate-pulse rounded-md bg-muted" />
      <template v-else-if="isAll">
        <EChart ref="allChart" :option="monthsOption" :height="240" :label="t('overview.allMonths')" />
        <p class="mt-3 text-sm text-caption">
          <template v-if="d.range.partial_before">{{ t('overview.partialBefore', { from: monthYear(d.range.partial_before.from), until: monthYear(d.range.partial_before.until), kwh: kwh(d.range.partial_before.wh, 1) }) }} </template>
          <template v-if="price != null">{{ t('overview.allPriceNote') }}</template>
        </p>
      </template>
      <EChart v-else ref="dailyChart" :option="dailyOption" :height="240" :label="t('overview.daily')" />
    </Section>

    <Section :title="t('overview.devices')" :summary="t('overview.devicesSort')">
      <div v-if="shares.length" class="mb-6">
        <div class="flex h-2 gap-0.5 overflow-hidden rounded-full" role="img" :aria-label="t('overview.shareLabel', { days: d?.range.days })">
          <span v-for="x in shares" :key="x.key" class="h-full first:rounded-l-full last:rounded-r-full" :style="{ background: x.css, flexGrow: x.share, flexBasis: 0 }" :title="`${x.label}: ${pct(x.share)}`" />
        </div>
        <ul class="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
          <li v-for="x in shares" :key="x.key" class="flex items-center gap-2">
            <span class="size-2.5 rounded-sm" :style="{ background: x.css }" aria-hidden="true" />
            <span class="text-muted-foreground">{{ x.label }}</span>
            <span class="font-medium tabular">{{ pct(x.share) }}</span>
          </li>
        </ul>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-xs text-caption">
              <th class="h-8 pr-3 text-left font-medium">{{ t('overview.col.device') }}</th>
              <th class="px-3 text-right font-medium">{{ t('overview.col.now') }}</th>
              <th class="hidden px-3 text-right font-medium sm:table-cell">{{ t('overview.col.today') }}</th>
              <th class="px-3 text-right font-medium">{{ d?.range.all ? t('overview.since', { since: monthYear(d.range.start) }) : t('overview.days', { n: d?.range.days }) }}</th>
              <th v-if="price != null" class="px-3 text-right font-medium">{{ t('overview.cost') }}</th>
              <th class="hidden px-3 text-right font-medium md:table-cell">{{ t('overview.col.trend') }}</th>
              <th class="hidden pl-3 text-right font-medium md:table-cell">{{ t('overview.col.share') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="x in rows" :key="x.id" tabindex="0"
                class="h-11 cursor-pointer border-t border-border transition-[background-color] hover:bg-muted focus-visible:outline-offset-[-2px]"
                @click="open(x.id)" @keydown.enter="open(x.id)">
              <td class="max-w-64 pr-3">
                <div class="flex min-w-0 items-center gap-2.5">
                  <span class="size-2.5 shrink-0 rounded-sm" :style="{ background: x.css }" aria-hidden="true" />
                  <span class="truncate font-medium" :class="x.on ? '' : 'text-muted-foreground'">{{ x.name }}</span>
                  <span v-if="x.room" class="hidden truncate text-xs text-caption sm:inline">{{ x.room }}</span>
                </div>
              </td>
              <td class="px-3 text-right">
                <span class="inline-flex items-center justify-end gap-2.5">
                  <span class="min-w-14 tabular" :class="x.on && (x.w ?? 0) >= 0.5 ? 'font-medium' : 'text-caption'">
                    {{ !x.on ? t('app.off') : x.w == null ? '–' : watts(x.w) }}
                  </span>
                  <span class="hidden h-1 w-16 overflow-hidden rounded-full bg-border sm:block" aria-hidden="true">
                    <span class="block h-full origin-left rounded-full bg-primary transition-transform duration-(--ease-settle-ms) ease-settle"
                          :style="{ transform: `scaleX(${x.bar.toFixed(3)})` }" />
                  </span>
                </span>
              </td>
              <td class="hidden px-3 text-right text-muted-foreground tabular sm:table-cell">{{ kwh(x.today_wh, 2) }}</td>
              <td class="px-3 text-right tabular">{{ kwh(x.range_wh) }}{{ NBSP }}kWh</td>
              <td v-if="price != null" class="px-3 text-right tabular">{{ eurFromWh(x.range_wh, price) }}</td>
              <td class="hidden px-3 text-right md:table-cell"><Sparkline :values="x.spark" class="inline-block" /></td>
              <td class="hidden pl-3 text-right text-muted-foreground tabular md:table-cell">{{ pct(x.share) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="h-10 border-t border-border-strong font-medium text-muted-foreground">
              <td class="pr-3">{{ t('overview.sumPlugs') }}</td>
              <td class="px-3 text-right tabular"><span class="inline-flex items-center justify-end gap-2.5"><span class="min-w-14">{{ totals.w == null ? '–' : watts(totals.w) }}</span><span class="hidden w-16 sm:block" aria-hidden="true" /></span></td>
              <td class="hidden px-3 text-right tabular sm:table-cell">{{ kwh(totals.today, 2) }}</td>
              <td class="px-3 text-right tabular">{{ kwh(totals.range) }}{{ NBSP }}kWh</td>
              <td v-if="price != null" class="px-3 text-right tabular">{{ eurFromWh(totals.range, price) }}</td>
              <td class="hidden md:table-cell" /><td class="hidden md:table-cell" />
            </tr>
          </tfoot>
        </table>
      </div>
    </Section>

    <div class="grid gap-x-12" :class="isAll ? '' : 'lg:grid-cols-2'">
      <Section v-if="!isAll" :title="t('overview.months')" :summary="monthsSummary">
        <div v-if="!d" class="h-[180px] animate-pulse rounded-md bg-muted" />
        <EChart v-else ref="monthsChart" :option="monthsOption" :height="180" :label="t('overview.months')" />
      </Section>
      <Section :title="t('overview.profile')" :summary="t('overview.profileDays', { n: d?.heat_days ?? 0 })" :class="isAll ? '' : 'border-t border-border lg:border-t-0'">
        <div v-if="!d" class="h-[180px] animate-pulse rounded-md bg-muted" />
        <EChart v-else :option="heatOption" :height="180" :label="t('overview.profile')" />
      </Section>
    </div>
  </div>
</template>
