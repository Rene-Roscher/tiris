<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import EChart from '@/components/charts/EChart.vue'
import Sparkline from '@/components/charts/Sparkline.vue'
import KpiTile from '@/components/KpiTile.vue'
import PageHeader from '@/components/PageHeader.vue'
import Panel from '@/components/Panel.vue'
import StateMessage from '@/components/StateMessage.vue'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useChartTheme } from '@/composables/useChartTheme'
import { useLive } from '@/composables/useLive'
import { ApiError, api } from '@/lib/api'
import { dayLong, dayShort, eurFromWh, kwh, money, monthLong, monthShort, NBSP, num, pct, watts } from '@/lib/format'
import type { Overview } from '@/lib/types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const theme = useChartTheme()
const live = useLive()

const RANGES = [7, 30, 90, 400] as const
const days = computed(() => { const d = Number(route.query.days); return RANGES.includes(d as never) ? d : 30 })
const device = computed(() => (typeof route.query.device === 'string' ? route.query.device : null))
const setQuery = (q: Record<string, string | undefined>) => router.replace({ query: { ...route.query, ...q } })

const q = useQuery({
  queryKey: computed(() => ['overview', days.value, device.value]),
  queryFn: () => api.get<Overview>(`/api/overview?days=${days.value}${device.value ? `&device=${encodeURIComponent(device.value)}` : ''}`),
  placeholderData: (prev) => prev,
  refetchInterval: 5 * 60_000,
})
const d = computed(() => q.data.value)
// 503 = no data yet (or no Tapo account): an empty state, not an error
const health = useQuery({ queryKey: ['health'], queryFn: () => api.get<{ tapo: boolean }>('/api/health'), staleTime: 60_000 })
const empty = computed(() => q.error.value instanceof ApiError && q.error.value.status === 503)
const k = computed(() => d.value?.kpi)
const price = computed(() => d.value?.price ?? null)
const devById = computed(() => Object.fromEntries((d.value?.devices ?? []).map((x) => [x.id, x])))
const selName = computed(() => (device.value ? devById.value[device.value]?.name : null))
const ratio = (a?: number | null, b?: number | null) => (a == null || !b ? null : a / b - 1)

const nowLabel = computed(() => new Intl.DateTimeFormat(undefined, { month: 'long' }).format(d.value ? new Date(d.value.now) : new Date()))
const monthProgress = computed(() => (k.value?.forecast_month_wh ? Math.min(1, k.value.mtd_wh / k.value.forecast_month_wh) : 0))
const avgDay = computed(() => (k.value?.range_wh ?? 0) / Math.max(1, d.value?.range.days ?? 1))

const livePower = computed(() => {
  const devs = live.snapshot.value?.devices ?? {}
  const ids = device.value ? [device.value] : Object.keys(devs)
  const vals = ids.map((id) => devs[id]?.w).filter((v): v is number => v != null)
  return { w: vals.length ? vals.reduce((a, b) => a + b, 0) : null, n: vals.length, of: live.snapshot.value?.known ?? ids.length }
})

const series = computed(() => (d.value?.series_keys ?? []).map((key) => {
  if (key === 'other') return { key, label: device.value ? selName.value ?? '' : t('overview.other'), slot: device.value ? 1 : 0 }
  const dev = devById.value[key]
  return { key, label: dev?.name ?? key, slot: dev?.slot ?? 0 }
}))

const dailyOption = computed<EChartsOption>(() => {
  const th = theme.value, rows = d.value?.daily ?? []
  const peak = d.value?.kpi.peak_day?.day
  return {
    ...th.base,
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: th.token('muted') } },
      valueFormatter: (v) => `${kwh(Number(v) * 1000)}${NBSP}kWh` },
    xAxis: { type: 'category', data: rows.map((r) => r.day), axisTick: { show: false }, axisLine: th.base.axisCommon.axisLine,
      axisLabel: { ...th.base.axisCommon.axisLabel, formatter: (v: string) => dayShort(v), hideOverlap: true } },
    yAxis: { type: 'value', splitLine: th.base.axisCommon.splitLine, axisLabel: { ...th.base.axisCommon.axisLabel, formatter: (v: number) => num(v) },
      name: 'kWh', nameGap: 12, nameTextStyle: { color: th.token('caption'), align: 'left' } },
    grid: { ...th.base.grid, top: 28 },
    series: series.value.map((s, i) => ({
      type: 'bar', stack: 'total', name: s.label, barMaxWidth: 22,
      itemStyle: { color: th.slotColor(s.slot), borderColor: th.token('card'), borderWidth: rows.length > 60 ? 0 : 1,
        borderRadius: i === series.value.length - 1 ? [4, 4, 0, 0] : 0 },
      emphasis: { focus: 'series' },
      data: rows.map((r) => +((r.by[s.key] ?? 0) / 1000).toFixed(3)),
      ...(i === series.value.length - 1 && peak ? {
        markPoint: undefined,
        label: { show: true, position: 'top', color: th.token('foreground'), fontWeight: 600, fontSize: 11,
          formatter: (p: { dataIndex: number }) => (rows[p.dataIndex]?.day === peak && rows.length <= 120 ? kwh(rows[p.dataIndex]!.total) : '') },
      } : {}),
    })),
  }
})

const monthsOption = computed<EChartsOption>(() => {
  const th = theme.value, ms = d.value?.months ?? [], fc = k.value?.forecast_month_wh ?? 0
  return {
    ...th.base,
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: th.token('muted') } },
      formatter: (ps: unknown) => {
        const p = (ps as { dataIndex: number }[])[0]!, m = ms[p.dataIndex]!
        const lines = [`<b>${monthLong(m.month)}</b>`, `${kwh(m.wh)}${NBSP}kWh${m.partial ? ` (${t('overview.soFar')})` : ''}`]
        if (price.value != null) lines.push(eurFromWh(m.wh, price.value))
        if (m.partial && fc) lines.push(`${t('overview.forecast')}: ${kwh(fc, 0)}${NBSP}kWh`)
        return lines.join('<br>')
      } },
    xAxis: { type: 'category', data: ms.map((m) => m.month), axisTick: { show: false }, axisLine: th.base.axisCommon.axisLine,
      axisLabel: { ...th.base.axisCommon.axisLabel, formatter: (v: string) => monthShort(v) } },
    yAxis: { type: 'value', splitLine: th.base.axisCommon.splitLine, axisLabel: { ...th.base.axisCommon.axisLabel, formatter: (v: number) => num(v) },
      name: 'kWh', nameGap: 12, nameTextStyle: { color: th.token('caption'), align: 'left' } },
    grid: { ...th.base.grid, top: 28 },
    series: [
      { type: 'bar', barGap: '-100%', barMaxWidth: 22, silent: true, z: 1,
        itemStyle: { color: 'transparent', borderColor: th.token('primary'), borderWidth: 1, borderType: 'solid', borderRadius: [4, 4, 0, 0] },
        data: ms.map((m) => (m.partial && fc > m.wh ? +(fc / 1000).toFixed(1) : null)) },
      { type: 'bar', barMaxWidth: 22, z: 2,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        data: ms.map((m) => ({ value: +(m.wh / 1000).toFixed(1), itemStyle: { color: th.token('chart-1'), opacity: m.partial ? 0.5 : 1 } })) },
    ],
  }
})

const heatOption = computed<EChartsOption>(() => {
  const th = theme.value, cells = d.value?.heat ?? []
  const dows = new Intl.DateTimeFormat(undefined, { weekday: 'short' })
  const dayNames = [1, 2, 3, 4, 5, 6, 7].map((i) => dows.format(new Date(2024, 0, i)))   // 2024-01-01 is a Monday
  const sorted = cells.map((c) => c.wh).sort((a, b) => a - b)
  // Scale to the 95th percentile, so one outlier hour does not wash out every other cell
  const max = Math.max(1, sorted[Math.floor(sorted.length * 0.95)] ?? 1)
  return {
    ...th.base,
    grid: { left: 4, right: 4, top: 4, bottom: 28, containLabel: true },
    tooltip: { ...th.base.tooltip, formatter: (p: unknown) => {
      const v = (p as { value: [number, number, number, number] }).value
      return `<b>${dayNames[v[1]]} ${String(v[0]).padStart(2, '0')}–${String(v[0] + 1).padStart(2, '0')}</b><br>${num(v[2])}${NBSP}Wh`
    } },
    xAxis: { type: 'category', data: Array.from({ length: 24 }, (_, i) => i), splitArea: { show: false }, axisTick: { show: false },
      axisLine: { show: false }, axisLabel: { ...th.base.axisCommon.axisLabel, interval: 5 } },
    yAxis: { type: 'category', data: dayNames, inverse: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: th.base.axisCommon.axisLabel },
    visualMap: { dimension: 2, min: 0, max, calculable: false, orient: 'horizontal', left: 'center', bottom: 0, itemHeight: 120, itemWidth: 8,
      text: [`≥${NBSP}${num(max)}${NBSP}Wh`, '0'], textStyle: { color: th.token('caption'), fontSize: 11 },
      inRange: { color: [1, 2, 3, 4, 5, 6, 7].map((i) => th.token(`seq-${i}`)) } },
    series: [{ type: 'heatmap', itemStyle: { borderColor: th.token('card'), borderWidth: 2, borderRadius: 3 },
      data: cells.map((c) => [c.hour, c.dow - 1, Math.round(c.wh), c.n]) }],
  }
})

const rows = computed(() => {
  const list = [...(d.value?.devices ?? [])].sort((a, b) => b.range_wh - a.range_wh)
  const total = list.reduce((s, x) => s + x.range_wh, 0)
  const max = Math.max(1, ...list.map((x) => x.range_wh))
  return list.map((x) => ({ ...x, share: total ? x.range_wh / total : 0, bar: x.range_wh / max }))
})
</script>

<template>
  <PageHeader :title="t('overview.title')">
    <Tabs v-if="!empty" :model-value="String(days)" @update:model-value="(v) => setQuery({ days: String(v) })">
      <TabsList>
        <TabsTrigger value="7">{{ t('overview.range.d7') }}</TabsTrigger>
        <TabsTrigger value="30">{{ t('overview.range.d30') }}</TabsTrigger>
        <TabsTrigger value="90">{{ t('overview.range.d90') }}</TabsTrigger>
        <TabsTrigger value="400">{{ t('overview.range.all') }}</TabsTrigger>
      </TabsList>
    </Tabs>
    <Select v-if="!empty" :model-value="device ?? 'all'" @update:model-value="(v) => setQuery({ device: v === 'all' ? undefined : String(v) })">
      <SelectTrigger class="h-9 w-52" :aria-label="t('overview.allDevices')"><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value="all">{{ t('overview.allDevices') }}</SelectItem>
        <SelectItem v-for="x in d?.devices ?? []" :key="x.id" :value="x.id">{{ x.name }}</SelectItem>
      </SelectContent>
    </Select>
  </PageHeader>

  <StateMessage v-if="empty && health.data.value?.tapo === false" kind="setup" :title="t('states.noTapoTitle')" :body="t('states.noTapoBody')" />
  <StateMessage v-else-if="empty" :title="t('states.noDataTitle')" :body="t('states.noDataBody')" />
  <StateMessage v-else-if="q.isError.value && !d" kind="error" :title="t('states.errorTitle')"
                :body="t('states.errorBody', { detail: String(q.error.value?.message ?? '') })" :action="t('common.retry')"
                :busy="q.isFetching.value" @action="q.refetch()" />
  <StateMessage v-else-if="q.isSuccess.value && !d?.devices.length" :title="t('states.noDataTitle')" :body="t('states.noDataBody')" />

  <div v-else class="flex flex-col gap-4 transition-opacity" :class="q.isFetching.value && d ? 'opacity-60' : ''">
    <!-- Hero: the one bold element of this view -->
    <section class="grid gap-6 rounded-lg border border-border bg-card p-6 lg:grid-cols-[1fr_1.4fr]">
      <div class="min-w-0">
        <p class="text-sm text-muted-foreground">{{ selName ?? t('overview.allDevices') }}, {{ t('overview.monthSoFar', { month: nowLabel }) }}</p>
        <div v-if="!k" class="mt-2 h-12 w-48 animate-pulse rounded-md bg-muted" />
        <p v-else class="mt-1 text-4xl font-semibold">{{ kwh(k.mtd_wh, 1) }}<span class="ml-2 text-lg font-medium text-muted-foreground">kWh</span></p>
        <p v-if="k && price != null" class="mt-1 text-lg font-medium">{{ eurFromWh(k.mtd_wh, price) }}</p>
        <RouterLink v-else-if="k" to="/costs" class="mt-1 inline-block text-sm text-link hover:underline">{{ t('overview.tariffHint') }}</RouterLink>
        <p v-if="k?.prev_month_same_wh" class="mt-3 text-sm"
           :class="(ratio(k.mtd_complete_wh, k.prev_month_same_wh) ?? 0) > 0 ? 'text-bad' : 'text-good'">
          <span class="tabular font-medium">{{ ((ratio(k.mtd_complete_wh, k.prev_month_same_wh) ?? 0) > 0 ? '+' : '') + pct(ratio(k.mtd_complete_wh, k.prev_month_same_wh)) }}</span>
          <span class="ml-1 text-caption">{{ t('overview.vsPrevMonth') }}</span>
        </p>
      </div>
      <div v-if="k" class="flex min-w-0 flex-col justify-center gap-3">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <span class="text-sm text-muted-foreground">{{ t('overview.forecastMonth') }}</span>
          <span class="font-semibold tabular">{{ kwh(k.forecast_month_wh, 0) }}{{ NBSP }}kWh<template v-if="price != null">, {{ eurFromWh(k.forecast_month_wh, price) }}</template></span>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-selection" role="meter" :aria-valuenow="Math.round(monthProgress * 100)" aria-valuemin="0" aria-valuemax="100" :aria-label="t('overview.forecastMonth')">
          <div class="h-full rounded-full bg-primary" :style="{ width: `${(monthProgress * 100).toFixed(1)}%` }" />
        </div>
        <dl class="mt-1 grid grid-cols-3 gap-4 text-sm">
          <div><dt class="text-muted-foreground">{{ t('overview.prevMonth') }}</dt><dd class="text-md font-semibold tabular">{{ kwh(k.prev_month_wh, 0) }}{{ NBSP }}kWh</dd>
            <dd v-if="price != null" class="text-caption">{{ eurFromWh(k.prev_month_wh, price) }}</dd></div>
          <div><dt class="text-muted-foreground">{{ t('overview.yearForecast') }}</dt><dd class="text-md font-semibold tabular">{{ kwh(k.forecast_year_wh, 0) }}{{ NBSP }}kWh</dd>
            <dd v-if="price != null" class="text-caption">{{ eurFromWh(k.forecast_year_wh, price, 0) }}</dd></div>
          <div><dt class="text-muted-foreground">{{ t('overview.avgPerDay') }}</dt><dd class="text-md font-semibold tabular">{{ kwh(avgDay) }}{{ NBSP }}kWh</dd>
            <dd class="text-caption">{{ t('overview.days', { n: d?.range.days }) }}</dd></div>
        </dl>
      </div>
    </section>

    <section class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiTile :label="t('overview.today')" :value="kwh(k?.today_wh)" unit="kWh" :loading="!k"
               :delta="ratio(k?.today_wh, k?.yesterday_same_time_wh)" :delta-label="t('overview.vsYesterday')"
               :sub="t('overview.yesterdayTotal', { value: `${kwh(k?.yesterday_wh)}${NBSP}kWh` })" />
      <KpiTile :label="t('overview.now')" :value="livePower.w == null ? '–' : num(livePower.w, livePower.w < 100 ? 1 : 0)" unit="W"
               :sub="livePower.w == null ? undefined : price != null ? t('overview.atThisLoad', { value: money(livePower.w * 24 / 1000 * price) }) : t('overview.plugsOnline', { n: livePower.n, of: livePower.of })" />
      <KpiTile :label="t('overview.last7')" :value="kwh(k?.last7_wh)" unit="kWh" :loading="!k"
               :delta="ratio(k?.last7_wh, k?.prev7_wh)" :delta-label="t('overview.vsPrev7')"
               :sub="price != null ? eurFromWh(k?.last7_wh, price) : undefined" />
      <KpiTile :label="t('overview.baseLoad')" :value="k?.base_w == null ? '–' : num(k.base_w)" unit="W" :loading="!k"
               :sub="k?.base_w == null ? t('overview.baseLoadMissing') : price != null ? t('overview.baseLoadSub', { kwh: num(k.base_w * 8.76), eur: money(k.base_w * 8.76 * price, 0) }) : t('overview.baseLoadSubKwh', { kwh: num(k.base_w * 8.76) })" />
    </section>

    <Panel :title="t('overview.daily')"
           :description="d ? `${dayShort(d.range.start)} – ${dayShort(d.range.end)}, ${kwh(k?.range_wh)} kWh${price != null ? `, ${eurFromWh(k?.range_wh, price)}` : ''}${k?.peak_day ? `. ${t('overview.peakDay', { day: dayLong(k.peak_day.day) })}` : ''}` : undefined">
      <ul v-if="series.length > 1" class="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
        <li v-for="s in series" :key="s.key" class="flex items-center gap-1.5">
          <span class="size-2.5 rounded-sm" :style="{ background: theme.slotColor(s.slot) }" aria-hidden="true" />{{ s.label }}
        </li>
      </ul>
      <div v-if="!d" class="h-[280px] animate-pulse rounded-md bg-muted" />
      <EChart v-else :option="dailyOption" :height="280" :label="t('overview.daily')" />
    </Panel>

    <section class="grid gap-4 lg:grid-cols-2">
      <Panel :title="t('overview.months')" :description="t('overview.monthsSub')">
        <div v-if="!d" class="h-[240px] animate-pulse rounded-md bg-muted" />
        <EChart v-else :option="monthsOption" :height="240" :label="t('overview.months')" />
      </Panel>
      <Panel :title="t('overview.profile')" :description="`${t('overview.profileSub')}, ${t('overview.profileDays', { n: d?.heat_days ?? 0 })}`">
        <div v-if="!d" class="h-[240px] animate-pulse rounded-md bg-muted" />
        <EChart v-else :option="heatOption" :height="240" :label="t('overview.profile')" />
      </Panel>
    </section>

    <Panel :title="t('overview.devices')" :description="t('overview.devicesSub')" :padded="false">
      <template #actions>
        <Button v-if="device" type="button" variant="ghost" size="sm" @click="setQuery({ device: undefined })">{{ t('overview.resetFilter') }}</Button>
      </template>
      <div class="overflow-x-auto px-2 pb-2 pt-3">
        <table class="w-full min-w-[760px] text-sm">
          <thead>
            <tr class="text-left text-caption">
              <th class="px-3 py-2 font-medium">{{ t('overview.col.device') }}</th>
              <th class="w-[22%] px-3 py-2 font-medium">{{ t('overview.days', { n: d?.range.days }) }}</th>
              <th class="px-3 py-2 text-right font-medium">kWh</th>
              <th v-if="price != null" class="px-3 py-2 text-right font-medium">EUR</th>
              <th class="px-3 py-2 text-right font-medium">{{ t('overview.col.share') }}</th>
              <th class="px-3 py-2 text-right font-medium">{{ t('overview.col.base') }}</th>
              <th class="px-3 py-2 text-right font-medium">{{ t('overview.col.now') }}</th>
              <th class="px-3 py-2 font-medium">{{ t('overview.col.trend') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="x in rows" :key="x.id" tabindex="0"
                class="cursor-pointer border-t border-border transition-[background-color] hover:bg-accent focus-visible:outline-offset-[-2px]"
                :class="device === x.id ? 'bg-selection hover:bg-selection' : ''" :aria-selected="device === x.id"
                @click="setQuery({ device: device === x.id ? undefined : x.id })" @keydown.enter="setQuery({ device: device === x.id ? undefined : x.id })">
              <td class="max-w-56 truncate px-3 py-2.5 font-medium">
                <span class="mr-2 inline-block size-2 rounded-full align-[1px]" :style="{ background: theme.slotColor(x.slot) }" aria-hidden="true" />{{ x.name }}
              </td>
              <td class="px-3 py-2.5"><div class="h-1.5 rounded-full bg-muted"><div class="h-full min-w-[2px] rounded-full bg-chart-1" :style="{ width: `${(x.bar * 100).toFixed(1)}%`, background: 'var(--chart-1)' }" /></div></td>
              <td class="px-3 py-2.5 text-right font-medium tabular">{{ kwh(x.range_wh) }}</td>
              <td v-if="price != null" class="px-3 py-2.5 text-right tabular">{{ eurFromWh(x.range_wh, price) }}</td>
              <td class="px-3 py-2.5 text-right text-muted-foreground tabular">{{ pct(x.share) }}</td>
              <td class="px-3 py-2.5 text-right text-muted-foreground tabular">{{ x.base_w == null ? '–' : watts(x.base_w) }}</td>
              <td class="px-3 py-2.5 text-right tabular">{{ live.snapshot.value?.devices[x.id] ? watts(live.snapshot.value.devices[x.id]!.w) : '–' }}</td>
              <td class="px-3 py-2.5"><Sparkline :values="x.spark" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>
  </div>
</template>
