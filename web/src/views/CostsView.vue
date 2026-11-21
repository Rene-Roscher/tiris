<script setup lang="ts">
import { CircleAlert, CircleCheck, Pencil, Plus } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import type { EChartsOption } from 'echarts'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import EChart from '@/components/charts/EChart.vue'
import CostsContract from '@/components/costs/CostsContract.vue'
import CostsPayments from '@/components/costs/CostsPayments.vue'
import CostsReadings from '@/components/costs/CostsReadings.vue'
import MeterDialog from '@/components/costs/MeterDialog.vue'
import Panel from '@/components/Panel.vue'
import Segmented from '@/components/Segmented.vue'
import StateMessage from '@/components/StateMessage.vue'
import { Button } from '@/components/ui/button'
import { useChartTheme } from '@/composables/useChartTheme'
import { mix } from '@/lib/charts'
import { useDevices } from '@/composables/useDevices'
import { api } from '@/lib/api'
import { dateMedium, money, monthLong, monthShort, NBSP, num } from '@/lib/format'
import type { Meter, MeterCosts } from '@/lib/types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const theme = useChartTheme()

const meters = useQuery({ queryKey: ['meters'], queryFn: () => api.get<Meter[]>('/api/meters') })
const active = computed(() => (meters.data.value ?? []).filter((m) => !m.archived))
const meterId = computed(() => {
  const want = Number(route.query.meter)
  return active.value.find((m) => m.id === want)?.id ?? active.value[0]?.id ?? null
})
const setMeter = (id: number) => router.replace({ query: { ...route.query, meter: String(id) } })
const meterOptions = computed(() => active.value.map((m) => ({ value: m.id, label: m.name })))
const q = useQuery({
  queryKey: computed(() => ['meter-costs', meterId.value]),
  queryFn: () => api.get<MeterCosts>(`/api/meters/${meterId.value}/costs`),
  enabled: computed(() => meterId.value != null),
  placeholderData: (p) => p,
})
const d = computed(() => (q.data.value?.meter.id === meterId.value ? q.data.value : undefined))
const b = computed(() => d.value?.billing)
const price = computed(() => d.value?.price_eur_kwh ?? null)
const tariff = computed(() => d.value?.tariffs.at(-1))

const { color: devColor } = useDevices()
const dialog = ref(false)
const editing = ref<Meter | null>(null)
function openDialog(m: Meter | null) { editing.value = m; dialog.value = true }

const verdict = computed(() => {
  const x = b.value?.balance
  if (x == null) return null
  if (x > 10) return { tone: 'warn', text: t('costs.backPayment', { amount: money(x, 0) }) }
  if (x < -10) return { tone: 'good', text: t('costs.refund', { amount: money(-x, 0) }) }
  return { tone: 'good', text: t('costs.balanced') }
})
const houseYearEur = computed(() => {
  const x = d.value
  return x?.house_kwh_year && price.value != null ? x.house_kwh_year * price.value + (x.base_eur_month ?? 0) * 12 : null
})
const standbyYear = computed(() => (d.value?.devices ?? []).reduce((s, x) => s + (x.standby_eur_year || 0), 0))
const standbyW = computed(() => (d.value?.devices ?? []).reduce((s, x) => s + (x.standby_w || 0), 0))
const maxDev = computed(() => Math.max(1, ...(d.value?.devices ?? []).map((x) => x.eur_year)))

const legend = computed(() => { const th = theme.value; return [th.token('primary'), mix(th.token('background'), th.token('primary'), 0.45), th.token('bar')] })
const monthsOption = computed<EChartsOption>(() => {
  const th = theme.value, ms = (d.value?.months ?? []).filter((m) => m.rest_eur != null)
  const keys = [
    { key: 'plugs_eur', label: t('costs.series.plugs'), color: th.token('primary') },
    { key: 'rest_eur', label: t('costs.series.rest'), color: mix(th.token('background'), th.token('primary'), 0.45) },
    { key: 'base_eur', label: t('costs.series.base'), color: th.token('bar') },
  ] as const
  return {
    ...th.base,
    grid: { left: 0, right: 0, top: 8, bottom: 0, containLabel: true },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'none' },
      formatter: (ps: unknown) => {
        const arr = ps as { dataIndex: number; seriesName: string; value: number; color: string }[]
        const m = ms[arr[0]!.dataIndex]!
        const total = (m.plugs_eur ?? 0) + (m.rest_eur ?? 0) + m.base_eur
        return [`<b>${monthLong(m.month)}</b>${m.partial ? ` (${t('overview.soFar')})` : ''}`, `<b>${money(total)}</b>`,
          ...arr.slice().reverse().map((p) => `<span style="display:inline-block;width:10px;height:2px;background:${p.color};margin-right:6px;vertical-align:middle"></span>${money(p.value)} ${p.seriesName}`)].join('<br>')
      } },
    xAxis: { type: 'category', data: ms.map((m) => m.month), axisTick: { show: false }, axisLine: { show: false },
      axisLabel: { color: th.token('caption'), fontSize: 11, formatter: (v: string) => monthShort(v) } },
    yAxis: { type: 'value', position: 'right', splitNumber: 3, splitLine: th.base.axisCommon.splitLine,
      axisLabel: { color: th.token('caption'), fontSize: 11, formatter: (v: number) => `${num(v)}${NBSP}€` } },
    series: keys.map((k, i) => ({
      type: 'bar', stack: 'cost', name: k.label, barMaxWidth: 26,
      itemStyle: { color: k.color, borderColor: th.token('background'), borderWidth: 1, borderRadius: i === keys.length - 1 ? [2, 2, 0, 0] : 0 },
      data: ms.map((m) => ({ value: +(m[k.key] ?? 0).toFixed(2), itemStyle: { opacity: m.partial ? 0.55 : 1 } })),
    })),
  }
})
</script>

<template>
  <div class="mb-7 flex min-h-9 flex-wrap items-center justify-between gap-3">
    <h1 class="font-semibold">{{ t('costs.title') }}</h1>
    <div class="flex flex-wrap items-center gap-2">
      <Segmented v-if="active.length > 1 && meterId != null" :model-value="meterId" :options="meterOptions" :label="t('costs.meter')" @update:model-value="(v) => setMeter(Number(v))" />
      <Button v-if="d" type="button" variant="ghost" size="sm" @click="openDialog(d.meter)"><Pencil class="size-4" aria-hidden="true" />{{ t('common.edit') }}</Button>
      <Button v-if="active.length" type="button" variant="outline" size="sm" @click="openDialog(null)"><Plus class="size-4" aria-hidden="true" />{{ t('costs.addMeter') }}</Button>
    </div>
  </div>

  <StateMessage v-if="meters.isError.value" kind="error" :title="t('states.errorTitle')" :body="t('states.errorBody', { detail: meters.error.value?.message ?? '' })"
                :action="t('common.retry')" @action="meters.refetch()" />
  <div v-else-if="meters.isLoading.value" class="h-48 animate-pulse rounded-lg bg-muted" />
  <StateMessage v-else-if="!active.length" kind="setup" :title="t('costs.noMeterTitle')" :body="t('costs.noMeterBody')" :action="t('costs.addMeter')" @action="openDialog(null)" />

  <div v-else class="flex flex-col divide-y divide-border transition-opacity" :class="q.isFetching.value && d ? 'opacity-60' : ''">
    <StateMessage v-if="q.isError.value && !d" kind="error" :title="t('states.errorTitle')" :body="t('states.errorBody', { detail: q.error.value?.message ?? '' })"
                  :action="t('common.retry')" @action="q.refetch()" />
    <div v-else-if="!d" class="mb-8 h-48 animate-pulse rounded-lg bg-muted" />
    <template v-else>
      <p v-if="d.warnings.includes('gas_conversion_missing')" class="flex flex-wrap items-center gap-x-3 gap-y-2 pb-6 text-sm">
        <span class="flex items-center gap-2"><CircleAlert class="size-4 text-warn" aria-hidden="true" />{{ t('costs.gasConversionMissing') }}</span>
        <Button type="button" variant="outline" size="sm" @click="openDialog(d.meter)">{{ t('common.edit') }}</Button>
      </p>

      <!-- hero: will the yearly bill bring a back payment? -->
      <section v-if="b" class="grid gap-6 pb-8 lg:grid-cols-[1fr_1.3fr] lg:gap-0 lg:divide-x lg:divide-border">
        <div class="min-w-0 lg:pr-8">
          <p class="text-xs font-medium text-caption">{{ t('costs.billingYear', { from: dateMedium(b.start), to: dateMedium(b.end) }) }}</p>
          <p class="mt-2 text-4xl font-semibold tabular">{{ money(b.cost_forecast, 0) }}</p>
          <p class="mt-1 text-sm text-muted-foreground">{{ t('costs.costForecast', { kwh: num(b.kwh_forecast) }) }}</p>
          <p v-if="verdict" class="mt-3 flex items-center gap-2 font-medium" :class="verdict.tone === 'warn' ? 'text-warn' : 'text-good'">
            <CircleAlert v-if="verdict.tone === 'warn'" class="size-4" aria-hidden="true" /><CircleCheck v-else class="size-4" aria-hidden="true" />{{ verdict.text }}
          </p>
          <p v-if="b.tariff_assumed" class="mt-2 text-sm text-caption">{{ t('costs.tariffAssumed') }}</p>
        </div>
        <div class="flex min-w-0 flex-col justify-center gap-5 border-t border-border pt-6 lg:border-t-0 lg:pl-8 lg:pt-0">
          <dl class="grid grid-cols-3 gap-4 text-sm">
            <div><dt class="text-xs text-caption">{{ t('costs.installmentsTotal') }}</dt><dd class="mt-1 font-semibold tabular">{{ money(b.installments_total, 0) }}</dd>
              <dd class="text-xs text-caption tabular">{{ b.installments_count }} × {{ money(b.installments_total / Math.max(1, b.installments_count)) }}</dd></div>
            <div><dt class="text-xs text-caption">{{ t('costs.paid') }}</dt><dd class="mt-1 font-semibold tabular">{{ money(b.installments_paid, 0) }}</dd>
              <dd class="text-xs text-caption">{{ b.paid_source === 'payments' ? t('costs.paidPayments') : t('costs.paidPlan') }}</dd></div>
            <div><dt class="text-xs text-caption">{{ t('costs.fairInstallment') }}</dt><dd class="mt-1 font-semibold tabular">{{ money(b.fair_installment) }}</dd>
              <dd class="text-xs text-caption">{{ t('costs.fairHint') }}</dd></div>
          </dl>
          <div class="grid gap-2 text-sm">
            <div class="flex justify-between gap-2"><span class="text-muted-foreground">{{ t('costs.timeElapsed') }}</span><span class="tabular">{{ b.elapsed_days }} / {{ b.total_days }}</span></div>
            <div class="h-1 overflow-hidden rounded-full bg-border-strong"><div class="h-full origin-left rounded-full bg-primary" :style="{ transform: `scaleX(${(b.elapsed_days / b.total_days).toFixed(3)})` }" /></div>
            <div class="mt-1.5 flex justify-between gap-2"><span class="text-muted-foreground">{{ t('costs.consumptionSoFar') }} ({{ b.kwh_so_far_measured ? t('costs.measured') : t('costs.estimated') }})</span>
              <span class="tabular">{{ num(b.kwh_so_far) }} / {{ num(b.kwh_forecast) }}{{ NBSP }}kWh</span></div>
            <div class="h-1 overflow-hidden rounded-full bg-border-strong"><div class="h-full origin-left rounded-full bg-primary" :style="{ transform: `scaleX(${Math.min(1, b.kwh_so_far / Math.max(1, b.kwh_forecast)).toFixed(3)})` }" /></div>
          </div>
        </div>
      </section>
      <p v-else class="pb-8 text-sm text-muted-foreground">{{ t('costs.needsReading') }}</p>

      <dl class="grid grid-cols-2 gap-x-8 gap-y-5 py-8 text-sm lg:grid-cols-4 lg:gap-0 lg:divide-x lg:divide-border">
        <div class="lg:pr-6"><dt class="text-xs text-caption">{{ t('costs.tariff') }}</dt>
          <dd class="mt-1 text-lg font-semibold tabular">{{ tariff ? num(tariff.energy_ct_gross, 2) : '–' }}<span class="ml-1 text-sm font-medium tracking-normal text-caption">ct/kWh</span></dd>
          <dd v-if="tariff" class="text-xs text-caption">{{ t('costs.basePrice', { value: money(tariff.base_eur_month_gross) }) }}<template v-if="tariff.contract_end">. {{ t('costs.contractUntil', { date: dateMedium(tariff.contract_end) }) }}</template></dd></div>
        <div class="lg:px-6"><dt class="text-xs text-caption">{{ t('costs.houseYear') }}</dt>
          <dd class="mt-1 text-lg font-semibold tabular">{{ d.house_kwh_year ? num(d.house_kwh_year) : '–' }}<span class="ml-1 text-sm font-medium tracking-normal text-caption">kWh</span></dd>
          <dd v-if="houseYearEur != null" class="text-xs text-caption">≈ {{ money(houseYearEur, 0) }}, {{ num(d.house_kwh_day, 2) }} kWh {{ t('costs.perDay') }}</dd></div>
        <template v-if="d.meter.kind === 'electricity'">
          <div class="lg:px-6"><dt class="text-xs text-caption">{{ t('costs.plugsShare') }}</dt>
            <dd class="mt-1 text-lg font-semibold tabular">{{ d.plugs_share != null ? num(d.plugs_share * 100) : '–' }}<span class="ml-1 text-sm font-medium tracking-normal text-caption">%</span></dd>
            <dd class="text-xs text-caption">{{ d.rest_kwh_day != null && price != null ? t('costs.restPerDay', { kwh: num(d.rest_kwh_day, 2), eur: money(d.rest_kwh_day * 365 * price, 0) }) : t('costs.needsTwoReadings') }}</dd></div>
          <div class="lg:pl-6"><dt class="text-xs text-caption">{{ t('costs.standby') }}</dt>
            <dd class="mt-1 text-lg font-semibold tabular">{{ num(standbyW) }}<span class="ml-1 text-sm font-medium tracking-normal text-caption">W</span></dd>
            <dd class="text-xs text-caption">{{ t('costs.standbySub', { eur: money(standbyYear, 0) }) }}</dd></div>
        </template>
      </dl>

      <Panel v-if="d.months?.some((m) => m.rest_eur != null)" :title="t('costs.monthly')" :description="t('costs.monthlySub')">
        <template #actions>
          <ul class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <li v-for="(k, i) in ['plugs', 'rest', 'base']" :key="k" class="flex items-center gap-1.5">
              <span class="size-2 rounded-sm" :style="{ background: legend[i] }" aria-hidden="true" />{{ t(`costs.series.${k}`) }}
            </li>
          </ul>
        </template>
        <EChart :option="monthsOption" :height="220" :label="t('costs.monthly')" />
      </Panel>

      <Panel v-if="d.devices?.length" :title="t('costs.perDevice')" :description="t('costs.perDeviceSub')">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[640px] text-sm">
            <thead><tr class="text-xs text-caption">
              <th class="h-8 pr-3 text-left font-medium">{{ t('overview.col.device') }}</th>
              <th class="w-[26%] px-3 text-left font-medium">{{ t('costs.col.perYear') }}</th>
              <th class="px-3 text-right font-medium">{{ t('costs.col.eurYear') }}</th>
              <th class="px-3 text-right font-medium">{{ t('common.perMonth') }}</th>
              <th class="px-3 text-right font-medium">{{ t('costs.col.kwhYear') }}</th>
              <th class="pl-3 text-right font-medium">{{ t('costs.col.standbyYear') }}</th>
            </tr></thead>
            <tbody>
              <tr v-for="x in d.devices" :key="x.id" class="h-11 border-t border-border">
                <td class="max-w-56 pr-3"><span class="flex min-w-0 items-center gap-2.5"><span class="size-2.5 shrink-0 rounded-sm" :style="{ background: devColor(x.id) }" aria-hidden="true" /><span class="truncate font-medium">{{ x.name }}</span></span></td>
                <td class="px-3"><div class="h-1 overflow-hidden rounded-full bg-border"><div class="h-full origin-left rounded-full" :style="{ background: devColor(x.id), transform: `scaleX(${(x.eur_year / maxDev).toFixed(3)})` }" /></div></td>
                <td class="px-3 text-right font-medium tabular">{{ money(x.eur_year) }}</td>
                <td class="px-3 text-right text-muted-foreground tabular">{{ money(x.eur_month) }}</td>
                <td class="px-3 text-right text-muted-foreground tabular">{{ num(x.kwh_year) }}</td>
                <td class="pl-3 text-right text-muted-foreground tabular">{{ x.standby_w ? `${money(x.standby_eur_year)} (${num(x.standby_w)}${NBSP}W)` : '–' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>

      <div class="grid items-start gap-x-12 xl:grid-cols-2">
        <CostsReadings :key="`r-${d.meter.id}`" :data="d" />
        <CostsContract :key="`c-${d.meter.id}`" :data="d" class="border-t border-border xl:border-t-0" />
      </div>
    </template>

    <CostsPayments :meters="active" />
  </div>

  <MeterDialog v-model:open="dialog" :meter="editing" @saved="(id) => setMeter(id)" />
</template>
