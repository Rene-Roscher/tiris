<script setup lang="ts">
import { Trash2 } from '@lucide/vue'
import { computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import Panel from '@/components/Panel.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAction } from '@/composables/useAction'
import { api } from '@/lib/api'
import { dateMedium, money, num } from '@/lib/format'
import type { MeterCosts } from '@/lib/types'

const props = defineProps<{ data: MeterCosts }>()
const { t } = useI18n()
const id = props.data.meter.id
const { busy, run } = useAction([['meter-costs', id], ['overview']], () => t('costs.tariffs'))
const n = (v: unknown) => (v === '' || v == null ? null : Number(String(v).replace(',', '.')))
const today = new Date().toLocaleDateString('sv-SE')

const tf = reactive({ valid_from: today, valid_to: '', provider: '', name: '', energy_ct_net: '', base_eur_year_net: '', vat_pct: '19', contract_end: '' })
const gross = computed(() => { const e = n(tf.energy_ct_net), v = n(tf.vat_pct); return e != null && v != null ? e * (1 + v / 100) : null })
async function addTariff() {
  const body = { valid_from: tf.valid_from, valid_to: tf.valid_to || null, provider: tf.provider || null, name: tf.name || null,
    energy_ct_net: n(tf.energy_ct_net), base_eur_year_net: n(tf.base_eur_year_net), vat_pct: n(tf.vat_pct), contract_end: tf.contract_end || null }
  if (await run(() => api.post(`/api/meters/${id}/tariffs`, body), t('common.saved'))) Object.assign(tf, { energy_ct_net: '', base_eur_year_net: '' })
}
const delTariff = (tid: number) => run(() => api.del(`/api/tariffs/${tid}`), t('common.deleted'))

const pf = reactive({ valid_from: today, valid_to: '', amount_gross: '', note: '' })
async function addPlan() {
  const body = { valid_from: pf.valid_from, valid_to: pf.valid_to || null, amount_gross: n(pf.amount_gross), note: pf.note || null }
  if (await run(() => api.post(`/api/meters/${id}/plans`, body), t('common.saved'))) Object.assign(pf, { amount_gross: '', note: '' })
}
const delPlan = (pid: number) => run(() => api.del(`/api/plans/${pid}`), t('common.deleted'))
</script>

<template>
  <Panel :title="t('costs.tariffs')">
    <ul v-if="data.tariffs.length" class="divide-y divide-border text-sm">
      <li v-for="x in [...data.tariffs].reverse()" :key="x.id" class="flex items-center gap-3 py-2">
        <div class="min-w-0 flex-1">
          <p><span class="font-medium tabular">{{ num(x.energy_ct_gross, 2) }} ct/kWh</span>
            <span class="text-caption"> ({{ num(x.energy_ct_net, 2) }} {{ t('costs.net') }})</span>,
            {{ t('costs.basePrice', { value: money(x.base_eur_month_gross) }) }}</p>
          <p class="text-caption">{{ [x.provider, x.name].filter(Boolean).join(', ') }}<template v-if="x.provider || x.name">: </template>
            {{ t('costs.validFrom') }} {{ dateMedium(x.valid_from) }}<template v-if="x.valid_to">, {{ t('costs.validTo') }} {{ dateMedium(x.valid_to) }}</template>
            <template v-if="x.contract_end">. {{ t('costs.contractUntil', { date: dateMedium(x.contract_end) }) }}</template></p>
        </div>
        <Button type="button" variant="ghost" size="icon-sm" :aria-label="t('common.delete')" :disabled="busy" @click="delTariff(x.id)"><Trash2 class="size-4" aria-hidden="true" /></Button>
      </li>
    </ul>
    <form class="mt-3 grid grid-cols-2 items-end gap-3 border-t border-border pt-4 md:grid-cols-3" @submit.prevent="addTariff">
      <div class="grid gap-1.5"><Label :for="`tf-from-${id}`">{{ t('costs.validFrom') }}</Label><Input :id="`tf-from-${id}`" v-model="tf.valid_from" type="date" required /></div>
      <div class="grid gap-1.5"><Label :for="`tf-to-${id}`">{{ t('costs.validTo') }}</Label><Input :id="`tf-to-${id}`" v-model="tf.valid_to" type="date" /></div>
      <div class="grid gap-1.5"><Label :for="`tf-ct-${id}`">{{ t('costs.energyPrice') }}</Label><Input :id="`tf-ct-${id}`" v-model="tf.energy_ct_net" inputmode="decimal" required placeholder="24,73…" class="tabular" /></div>
      <div class="grid gap-1.5"><Label :for="`tf-base-${id}`">{{ t('costs.baseYear') }}</Label><Input :id="`tf-base-${id}`" v-model="tf.base_eur_year_net" inputmode="decimal" required placeholder="122,00…" class="tabular" /></div>
      <div class="grid gap-1.5"><Label :for="`tf-vat-${id}`">{{ t('costs.vat') }}</Label><Input :id="`tf-vat-${id}`" v-model="tf.vat_pct" inputmode="decimal" class="tabular" /></div>
      <div class="grid gap-1.5"><Label :for="`tf-prov-${id}`">{{ t('costs.provider') }}</Label><Input :id="`tf-prov-${id}`" v-model="tf.provider" maxlength="80" /></div>
      <div class="grid gap-1.5"><Label :for="`tf-end-${id}`">{{ t('costs.contractEnd') }}</Label><Input :id="`tf-end-${id}`" v-model="tf.contract_end" type="date" /></div>
      <div class="col-span-full flex flex-wrap items-center justify-end gap-3"><span class="text-sm text-caption tabular">{{ gross != null ? t('costs.gross', { value: `${num(gross, 2)} ct` }) : '' }}</span>
        <Button type="submit" variant="outline" :disabled="busy">{{ t('costs.addTariff') }}</Button></div>
    </form>

    <div class="mt-6 border-t border-border pt-4">
      <h3 class="font-medium">{{ t('costs.plans') }}</h3>
      <p class="mt-0.5 text-sm text-muted-foreground">{{ t('costs.plansSub') }}</p>
      <ul v-if="data.plans.length" class="mt-2 divide-y divide-border text-sm">
        <li v-for="p in [...data.plans].reverse()" :key="p.id" class="flex items-center gap-3 py-2">
          <span class="w-24 font-medium tabular">{{ money(p.amount_gross) }}</span>
          <span class="flex-1 text-muted-foreground">{{ dateMedium(p.valid_from) }} – {{ p.valid_to ? dateMedium(p.valid_to) : t('common.open') }}
            <span v-if="p.note" class="text-caption">, {{ p.note }}</span></span>
          <Button type="button" variant="ghost" size="icon-sm" :aria-label="t('common.delete')" :disabled="busy" @click="delPlan(p.id)"><Trash2 class="size-4" aria-hidden="true" /></Button>
        </li>
      </ul>
      <form class="mt-3 flex flex-wrap items-end gap-3" @submit.prevent="addPlan">
        <div class="grid gap-1.5"><Label :for="`pl-amt-${id}`">{{ t('costs.planAmount') }}</Label><Input :id="`pl-amt-${id}`" v-model="pf.amount_gross" inputmode="decimal" required class="w-28 tabular" placeholder="62,00…" /></div>
        <div class="grid gap-1.5"><Label :for="`pl-from-${id}`">{{ t('costs.firstDue') }}</Label><Input :id="`pl-from-${id}`" v-model="pf.valid_from" type="date" required class="w-40" /></div>
        <div class="grid gap-1.5"><Label :for="`pl-to-${id}`">{{ t('costs.lastDue') }}</Label><Input :id="`pl-to-${id}`" v-model="pf.valid_to" type="date" class="w-40" /></div>
        <Button type="submit" variant="outline" :disabled="busy">{{ t('costs.addPlan') }}</Button>
      </form>
    </div>
  </Panel>
</template>
