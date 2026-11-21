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
import KpiTile from '@/components/KpiTile.vue'
import PageHeader from '@/components/PageHeader.vue'
import Panel from '@/components/Panel.vue'
import StateMessage from '@/components/StateMessage.vue'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useChartTheme } from '@/composables/useChartTheme'
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

const monthsOption = computed<EChartsOption>(() => {
  const th = theme.value, ms = (d.value?.months ?? []).filter((m) => m.rest_eur != null)
  const keys = [
    { key: 'plugs_eur', label: t('costs.series.plugs'), color: th.token('chart-1') },
    { key: 'rest_eur', label: t('costs.series.rest'), color: th.token('chart-2') },
    { key: 'base_eur', label: t('costs.series.base'), color: th.token('chart-other') },
  ] as const
  return {
    ...th.base,
    grid: { ...th.base.grid, top: 28 },
    tooltip: { ...th.base.tooltip, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: th.token('muted') } },
      formatter: (ps: unknown) => {
        const arr = ps as { dataIndex: number; seriesName: string; value: number; color: string }[]
        const m = ms[arr[0]!.dataIndex]!
        const total = (m.plugs_eur ?? 0) + (m.rest_eur ?? 0) + m.base_eur
        return [`<b>${monthLong(m.month)}</b>${m.partial ? ` (${t('overview.soFar')})` : ''}`, `<b>${money(total)}</b>`,
          ...arr.slice().reverse().map((p) => `<span style="display:inline-block;width:10px;height:2px;background:${p.color};margin-right:6px;vertical-align:middle"></span>${money(p.value)} ${p.seriesName}`)].join('<br>')
      } },
    xAxis: { type: 'category', data: ms.map((m) => m.month), axisTick: { show: false }, axisLine: th.base.axisCommon.axisLine,
      axisLabel: { ...th.base.axisCommon.axisLabel, formatter: (v: string) => monthShort(v) } },
    yAxis: { type: 'value', splitLine: th.base.axisCommon.splitLine, name: '€', nameGap: 12,
      nameTextStyle: { color: th.token('caption'), align: 'left' },
      axisLabel: { ...th.base.axisCommon.axisLabel, formatter: (v: number) => num(v) } },
    series: keys.map((k, i) => ({
      type: 'bar', stack: 'cost', name: k.label, barMaxWidth: 26,
      itemStyle: { color: k.color, borderColor: th.token('card'), borderWidth: 1, borderRadius: i === keys.length - 1 ? [4, 4, 0, 0] : 0 },
      data: ms.map((m) => ({ value: +(m[k.key] ?? 0).toFixed(2), itemStyle: { opacity: m.partial ? 0.55 : 1 } })),
    })),
  }
})
</script>

<template>
  <PageHeader :title="t('costs.title')">
    <Tabs v-if="active.length > 1" :model-value="String(meterId)" @update:model-value="(v) => setMeter(Number(v))">
      <TabsList><TabsTrigger v-for="m in active" :key="m.id" :value="String(m.id)">{{ m.name }}</TabsTrigger></TabsList>
    </Tabs>
    <Button v-if="d" type="button" variant="outline" size="sm" @click="openDialog(d.meter)"><Pencil class="size-4" aria-hidden="true" />{{ t('common.edit') }}</Button>
    <Button v-if="active.length" type="button" size="sm" @click="openDialog(null)"><Plus class="size-4" aria-hidden="true" />{{ t('costs.addMeter') }}</Button>
  </PageHeader>

  <StateMessage v-if="meters.isError.value" kind="error" :title="t('states.errorTitle')" :body="t('states.errorBody', { detail: meters.error.value?.message ?? '' })"
                :action="t('common.retry')" @action="meters.refetch()" />
  <div v-else-if="meters.isLoading.value" class="h-48 animate-pulse rounded-lg bg-muted" />
  <div v-else-if="!active.length" class="rounded-lg border border-border bg-card">
    <StateMessage kind="setup" :title="t('costs.noMeterTitle')" :body="t('costs.noMeterBody')" :action="t('costs.addMeter')" @action="openDialog(null)" />
  </div>

  <div v-else class="flex flex-col gap-4 transition-opacity duration-200" :class="q.isFetching.value && d ? 'opacity-60' : ''">
    <StateMessage v-if="q.isError.value && !d" kind="error" :title="t('states.errorTitle')" :body="t('states.errorBody', { detail: q.error.value?.message ?? '' })"
                  :action="t('common.retry')" @action="q.refetch()" />
    <div v-else-if="!d" class="h-48 animate-pulse rounded-lg bg-muted" />
    <template v-else>
      <div v-if="d.warnings.includes('gas_conversion_missing')" class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-5 py-3 text-sm">
        <span class="flex items-center gap-2"><CircleAlert class="size-4 text-warn" aria-hidden="true" />{{ t('costs.gasConversionMissing') }}</span>
        <Button type="button" variant="outline" size="sm" @click="openDialog(d.meter)">{{ t('common.edit') }}</Button>
      </div>
      <!-- the one bold element: will the yearly bill bring a back payment? -->
      <section v-if="b" class="grid gap-6 rounded-lg border border-border bg-card p-6 lg:grid-cols-[1fr_1.4fr]">
        <div class="min-w-0">
          <p class="text-sm text-muted-foreground">{{ t('costs.billingYear', { from: dateMedium(b.start), to: dateMedium(b.end) }) }}</p>
          <p class="mt-1 text-4xl font-semibold">{{ money(b.cost_forecast, 0) }}</p>
          <p class="text-sm text-muted-foreground">{{ t('costs.costForecast', { kwh: num(b.kwh_forecast) }) }}</p>
          <p v-if="verdict" class="mt-3 flex items-center gap-2 font-medium" :class="verdict.tone === 'warn' ? 'text-warn' : 'text-good'">
            <CircleAlert v-if="verdict.tone === 'warn'" class="size-4" aria-hidden="true" /><CircleCheck v-else class="size-4" aria-hidden="true" />{{ verdict.text }}
          </p>
          <p v-if="b.tariff_assumed" class="mt-2 text-sm text-caption">{{ t('costs.tariffAssumed') }}</p>
        </div>
        <div class="flex min-w-0 flex-col justify-center gap-4">
          <dl class="grid grid-cols-3 gap-4 text-sm">
            <div><dt class="text-muted-foreground">{{ t('costs.installmentsTotal') }}</dt><dd class="text-md font-semibold tabular">{{ money(b.installments_total, 0) }}</dd>
              <dd class="text-caption tabular">{{ b.installments_count }} × {{ money(b.installments_total / Math.max(1, b.installments_count)) }}</dd></div>
            <div><dt class="text-muted-foreground">{{ t('costs.paid') }}</dt><dd class="text-md font-semibold tabular">{{ money(b.installments_paid, 0) }}</dd>
              <dd class="text-caption">{{ b.paid_source === 'payments' ? t('costs.paidPayments') : t('costs.paidPlan') }}</dd></div>
            <div><dt class="text-muted-foreground">{{ t('costs.fairInstallment') }}</dt><dd class="text-md font-semibold tabular">{{ money(b.fair_installment) }}</dd>
              <dd class="text-caption">{{ t('costs.fairHint') }}</dd></div>
          </dl>
          <div class="grid gap-1.5 text-sm">
            <div class="flex justify-between gap-2"><span class="text-muted-foreground">{{ t('costs.timeElapsed') }}</span><span class="tabular">{{ b.elapsed_days }} / {{ b.total_days }}</span></div>
            <div class="h-2 overflow-hidden rounded-full bg-selection"><div class="h-full rounded-full bg-primary" :style="{ width: `${(b.elapsed_days / b.total_days * 100).toFixed(1)}%` }" /></div>
            <div class="mt-1 flex justify-between gap-2"><span class="text-muted-foreground">{{ t('costs.consumptionSoFar') }} ({{ b.kwh_so_far_measured ? t('costs.measured') : t('costs.estimated') }})</span>
              <span class="tabular">{{ num(b.kwh_so_far) }} / {{ num(b.kwh_forecast) }}{{ NBSP }}kWh</span></div>
            <div class="h-2 overflow-hidden rounded-full bg-selection"><div class="h-full rounded-full bg-primary" :style="{ width: `${Math.min(100, b.kwh_so_far / Math.max(1, b.kwh_forecast) * 100).toFixed(1)}%` }" /></div>
          </div>
        </div>
      </section>
      <div v-else class="rounded-lg border border-border bg-card px-5 py-4 text-sm text-muted-foreground">{{ t('costs.needsReading') }}</div>

      <section class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile :label="t('costs.tariff')" :value="tariff ? num(tariff.energy_ct_gross, 2) : '–'" unit="ct/kWh"
                 :sub="tariff ? `${t('costs.basePrice', { value: money(tariff.base_eur_month_gross) })}${tariff.contract_end ? `. ${t('costs.contractUntil', { date: dateMedium(tariff.contract_end) })}` : ''}` : undefined" />
        <KpiTile :label="t('costs.houseYear')" :value="d.house_kwh_year ? num(d.house_kwh_year) : '–'" unit="kWh"
                 :sub="houseYearEur != null ? `≈ ${money(houseYearEur, 0)}, ${num(d.house_kwh_day, 2)} kWh ${t('costs.perDay')}` : undefined" />
        <template v-if="d.meter.kind === 'electricity'">
          <KpiTile :label="t('costs.plugsShare')" :value="d.plugs_share != null ? num(d.plugs_share * 100) : '–'" unit="%"
                   :sub="d.rest_kwh_day != null && price != null ? t('costs.restPerDay', { kwh: num(d.rest_kwh_day, 2), eur: money(d.rest_kwh_day * 365 * price, 0) }) : t('costs.needsTwoReadings')" />
          <KpiTile :label="t('costs.standby')" :value="num(standbyW)" unit="W" :sub="t('costs.standbySub', { eur: money(standbyYear, 0) })" />
        </template>
      </section>

      <Panel v-if="d.months?.some((m) => m.rest_eur != null)" :title="t('costs.monthly')" :description="t('costs.monthlySub')">
        <ul class="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <li v-for="(k, i) in ['plugs', 'rest', 'base']" :key="k" class="flex items-center gap-1.5">
            <span class="size-2.5 rounded-sm" :style="{ background: theme.token(['chart-1', 'chart-2', 'chart-other'][i]!) }" aria-hidden="true" />{{ t(`costs.series.${k}`) }}
          </li>
        </ul>
        <EChart :option="monthsOption" :height="260" :label="t('costs.monthly')" />
      </Panel>

      <Panel v-if="d.devices?.length" :title="t('costs.perDevice')" :description="t('costs.perDeviceSub')" :padded="false">
        <div class="overflow-x-auto px-2 pb-2 pt-3">
          <table class="w-full min-w-[640px] text-sm">
            <thead><tr class="text-left text-caption">
              <th class="px-3 py-2 font-medium">{{ t('overview.col.device') }}</th>
              <th class="w-[28%] px-3 py-2 font-medium">{{ t('costs.col.perYear') }}</th>
              <th class="px-3 py-2 text-right font-medium">{{ t('costs.col.eurYear') }}</th>
              <th class="px-3 py-2 text-right font-medium">{{ t('common.perMonth') }}</th>
              <th class="px-3 py-2 text-right font-medium">{{ t('costs.col.kwhYear') }}</th>
              <th class="px-3 py-2 text-right font-medium">{{ t('costs.col.standbyYear') }}</th>
            </tr></thead>
            <tbody>
              <tr v-for="x in d.devices" :key="x.id" class="border-t border-border">
                <td class="max-w-56 truncate px-3 py-2.5 font-medium">{{ x.name }}</td>
                <td class="px-3 py-2.5"><div class="h-1.5 rounded-full bg-muted"><div class="h-full min-w-[2px] rounded-full bg-primary" :style="{ width: `${(x.eur_year / maxDev * 100).toFixed(1)}%` }" /></div></td>
                <td class="px-3 py-2.5 text-right font-medium tabular">{{ money(x.eur_year) }}</td>
                <td class="px-3 py-2.5 text-right text-muted-foreground tabular">{{ money(x.eur_month) }}</td>
                <td class="px-3 py-2.5 text-right text-muted-foreground tabular">{{ num(x.kwh_year) }}</td>
                <td class="px-3 py-2.5 text-right text-muted-foreground tabular">{{ x.standby_w ? `${money(x.standby_eur_year)} (${num(x.standby_w)}${NBSP}W)` : '–' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>

      <section class="grid items-start gap-4 xl:grid-cols-2">
        <CostsReadings :key="`r-${d.meter.id}`" :data="d" />
        <CostsContract :key="`c-${d.meter.id}`" :data="d" />
      </section>
    </template>

    <CostsPayments :meters="active" />
  </div>

  <MeterDialog v-model:open="dialog" :meter="editing" @saved="(id) => setMeter(id)" />
</template>
