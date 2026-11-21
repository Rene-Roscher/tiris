<script setup lang="ts">
import { Trash2 } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Panel from '@/components/Panel.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAction } from '@/composables/useAction'
import { api } from '@/lib/api'
import { dateMedium, money } from '@/lib/format'
import type { Meter, PaymentsResponse } from '@/lib/types'

const props = defineProps<{ meters: Meter[] }>()
const { t } = useI18n()
const q = useQuery({ queryKey: ['payments'], queryFn: () => api.get<PaymentsResponse>('/api/payments') })
const { busy, run } = useAction([['payments'], ['meter-costs']], () => t('costs.payments'))
const filter = ref('all')
const meterName = (id?: number | null) => props.meters.find((m) => m.id === id)?.name
const kinds = computed(() => [...new Set(props.meters.map((m) => m.kind))])
const list = computed(() => (q.data.value?.payments ?? []).filter((p) =>
  filter.value === 'all' || (filter.value === 'none' ? !p.meter_id : String(p.meter_id) === filter.value)))
const unassigned = computed(() => (q.data.value?.payments ?? []).filter((p) => !p.meter_id).length)
const months = (y: number) => (y === new Date().getFullYear() ? new Date().getMonth() + 1 : 12)

const today = new Date().toLocaleDateString('sv-SE')
const f = reactive({ day: today, amount: '', kind: 'installment', meter_id: props.meters[0] ? String(props.meters[0].id) : 'none', note: '' })
async function add() {
  const amount = Number(String(f.amount).replace(',', '.'))
  if (!Number.isFinite(amount)) return
  const body = { day: f.day, amount, kind: f.kind, meter_id: f.meter_id === 'none' ? null : Number(f.meter_id), note: f.note || null }
  if (await run(() => api.post('/api/payments', body), t('common.saved'))) Object.assign(f, { amount: '', note: '' })
}
const assign = (id: number, v: string) => run(() => api.patch(`/api/payments/${id}`, { meter_id: v === 'none' ? null : Number(v) }))
const remove = (id: number) => run(() => api.del(`/api/payments/${id}`), t('common.deleted'))
</script>

<template>
  <Panel :title="t('costs.payments')" :description="t('costs.paymentsSub')">
    <template #actions>
      <span v-if="unassigned" class="rounded-full bg-warn-fill px-2 py-px text-xs font-medium text-black">{{ t('costs.unassignedCount', { n: unassigned }) }}</span>
    </template>
    <div v-if="q.data.value?.by_year.length" class="overflow-x-auto">
      <table class="w-full min-w-[520px] text-sm">
        <thead><tr class="text-left text-caption">
          <th class="py-1.5 pr-3 font-medium">{{ t('costs.byYear') }}</th>
          <th v-for="k in kinds" :key="k" class="px-3 py-1.5 text-right font-medium">{{ t(`costs.kind.${k}`) }}</th>
          <th v-if="q.data.value.by_year.some((y) => y.unassigned)" class="px-3 py-1.5 text-right font-medium">{{ t('costs.unassigned') }}</th>
          <th class="px-3 py-1.5 text-right font-medium">{{ t('costs.total') }}</th>
          <th class="pl-3 py-1.5 text-right font-medium">{{ t('costs.avgMonth') }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="y in q.data.value.by_year" :key="y.year" class="border-t border-border">
            <td class="py-2 pr-3 font-medium tabular">{{ y.year }}</td>
            <td v-for="k in kinds" :key="k" class="px-3 py-2 text-right tabular">{{ y[k] != null ? money(y[k]) : '–' }}</td>
            <td v-if="q.data.value.by_year.some((x) => x.unassigned)" class="px-3 py-2 text-right tabular text-muted-foreground">{{ y.unassigned != null ? money(y.unassigned) : '–' }}</td>
            <td class="px-3 py-2 text-right font-medium tabular">{{ money(y.total) }}</td>
            <td class="py-2 pl-3 text-right tabular text-muted-foreground">{{ money(y.total / months(y.year)) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <details class="mt-4" :open="unassigned > 0">
      <summary class="cursor-pointer text-sm text-muted-foreground">{{ t('costs.bookings', { n: q.data.value?.payments.length ?? 0 }) }}</summary>
      <Tabs v-model="filter" class="mt-3">
        <TabsList>
          <TabsTrigger value="all">{{ t('common.all') }}</TabsTrigger>
          <TabsTrigger v-for="m in meters" :key="m.id" :value="String(m.id)">{{ m.name }}</TabsTrigger>
          <TabsTrigger value="none">{{ t('costs.unassigned') }}</TabsTrigger>
        </TabsList>
      </Tabs>
      <div class="mt-2 max-h-96 overflow-auto">
        <table class="w-full min-w-[560px] text-sm">
          <tbody>
            <tr v-for="p in list" :key="p.id" class="border-t border-border">
              <td class="py-1.5 pr-3 whitespace-nowrap tabular">{{ dateMedium(p.day) }}</td>
              <td class="px-3 py-1.5 text-right font-medium tabular whitespace-nowrap" :class="p.amount < 0 ? 'text-good' : ''">{{ money(p.amount) }}</td>
              <td class="px-3 py-1.5">
                <Select :model-value="p.meter_id ? String(p.meter_id) : 'none'" :disabled="busy" @update:model-value="(v) => assign(p.id, String(v))">
                  <SelectTrigger class="h-7 w-44 text-sm" :aria-label="meterName(p.meter_id) ?? t('costs.unassigned')"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem v-for="m in meters" :key="m.id" :value="String(m.id)">{{ m.name }}</SelectItem>
                    <SelectItem value="none">{{ t('costs.unassigned') }}</SelectItem>
                  </SelectContent>
                </Select>
              </td>
              <td class="px-3 py-1.5 text-muted-foreground">{{ t(`costs.paymentKind.${p.kind}`) }}<template v-if="p.note">, {{ p.note }}</template></td>
              <td class="py-1.5 pl-3 text-right">
                <Button type="button" variant="ghost" size="icon-sm" :aria-label="t('common.delete')" :disabled="busy" @click="remove(p.id)"><Trash2 class="size-4" aria-hidden="true" /></Button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>

    <form class="mt-4 flex flex-wrap items-end gap-3 border-t border-border pt-4" @submit.prevent="add">
      <div class="grid gap-1.5"><Label for="pay-day">{{ t('common.date') }}</Label><Input id="pay-day" v-model="f.day" type="date" required class="w-40" /></div>
      <div class="grid gap-1.5"><Label for="pay-amt">{{ t('common.amount') }} (€)</Label><Input id="pay-amt" v-model="f.amount" inputmode="decimal" required class="w-28 tabular" placeholder="62,00…" /></div>
      <div class="grid gap-1.5"><Label>{{ t('common.kind') }}</Label>
        <Select v-model="f.kind"><SelectTrigger class="w-40"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem v-for="k in ['installment', 'settlement', 'other']" :key="k" :value="k">{{ t(`costs.paymentKind.${k}`) }}</SelectItem></SelectContent></Select></div>
      <div class="grid gap-1.5"><Label>{{ t('costs.meters') }}</Label>
        <Select v-model="f.meter_id"><SelectTrigger class="w-44"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem v-for="m in meters" :key="m.id" :value="String(m.id)">{{ m.name }}</SelectItem>
            <SelectItem value="none">{{ t('costs.unassigned') }}</SelectItem></SelectContent></Select></div>
      <div class="grid gap-1.5"><Label for="pay-note">{{ t('common.note') }}</Label><Input id="pay-note" v-model="f.note" maxlength="200" class="w-48" /></div>
      <Button type="submit" :disabled="busy">{{ t('costs.addPayment') }}</Button>
    </form>
  </Panel>
</template>
