<script setup lang="ts">
import { Trash2 } from '@lucide/vue'
import { reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import Panel from '@/components/Panel.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useAction } from '@/composables/useAction'
import { api } from '@/lib/api'
import { dateMedium, num, pct } from '@/lib/format'
import type { MeterCosts } from '@/lib/types'

const props = defineProps<{ data: MeterCosts }>()
const { t } = useI18n()
const id = props.data.meter.id
const { busy, run } = useAction([['meter-costs', id]], () => t('costs.readings'))
const today = new Date().toLocaleDateString('sv-SE')
const f = reactive({ day: today, value: '', estimated: false })
const unit = props.data.meter.unit === 'm3' ? 'm³' : 'kWh'
async function add() {
  const value = Number(String(f.value).replace(/\./g, '').replace(',', '.'))
  if (!Number.isFinite(value)) return
  const ok = await run(() => api.post(`/api/meters/${id}/readings`, { day: f.day, value, estimated: f.estimated }), t('common.saved'))
  if (ok) f.value = ''
}
const remove = (day: string) => run(() => api.del(`/api/meters/${id}/readings/${day}`), t('common.deleted'))
</script>

<template>
  <Panel :title="t('costs.readings')" :description="t('costs.readingsSub')">
    <div v-if="data.intervals.length" class="overflow-x-auto">
      <table class="w-full min-w-[440px] text-sm">
        <thead><tr class="text-left text-caption">
          <th class="py-1.5 pr-3 font-medium">{{ t('costs.interval') }}</th>
          <th class="px-3 py-1.5 text-right font-medium">kWh</th>
          <th class="px-3 py-1.5 text-right font-medium">{{ t('costs.perDay') }}</th>
          <th v-if="data.meter.kind === 'electricity'" class="pl-3 py-1.5 text-right font-medium">{{ t('costs.coverage') }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="iv in [...data.intervals].reverse()" :key="iv.from" class="border-t border-border">
            <td class="py-2 pr-3 tabular">{{ dateMedium(iv.from) }} – {{ dateMedium(iv.to) }}<span v-if="iv.estimated" class="text-caption">, {{ t('costs.estimated') }}</span></td>
            <td class="px-3 py-2 text-right tabular">{{ num(iv.kwh) }}</td>
            <td class="px-3 py-2 text-right tabular">{{ num(iv.kwh_day, 2) }}</td>
            <td v-if="data.meter.kind === 'electricity'" class="py-2 pl-3 text-right tabular text-muted-foreground">
              {{ iv.coverage != null ? pct(iv.coverage) : t('costs.noPlugData') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <details v-if="data.readings.length" class="mt-3 text-sm">
      <summary class="cursor-pointer text-muted-foreground">{{ t('costs.readingsCount', { n: data.readings.length }) }}</summary>
      <ul class="mt-2 divide-y divide-border">
        <li v-for="r in [...data.readings].reverse()" :key="r.day" class="flex items-center gap-3 py-1.5">
          <span class="w-28">{{ dateMedium(r.day) }}</span>
          <span class="flex-1 tabular">{{ num(r.value, 1) }} {{ unit }}<span v-if="r.estimated" class="text-caption">, {{ t('costs.estimated') }}</span>
            <span v-if="r.note" class="text-caption">, {{ r.note }}</span></span>
          <Button type="button" variant="ghost" size="icon-sm" :aria-label="t('common.delete')" :disabled="busy" @click="remove(r.day)"><Trash2 class="size-4" aria-hidden="true" /></Button>
        </li>
      </ul>
    </details>
    <form class="mt-4 flex flex-wrap items-end gap-3 border-t border-border pt-4" @submit.prevent="add">
      <div class="grid gap-1.5"><Label :for="`rd-day-${id}`">{{ t('common.date') }}</Label><Input :id="`rd-day-${id}`" v-model="f.day" type="date" :max="today" required class="w-40" /></div>
      <div class="grid gap-1.5"><Label :for="`rd-val-${id}`">{{ t('costs.readingValue') }} ({{ unit }})</Label>
        <Input :id="`rd-val-${id}`" v-model="f.value" inputmode="decimal" required class="w-36 text-right tabular" placeholder="12.840…" /></div>
      <div class="flex h-9 items-center gap-2"><Switch :id="`rd-est-${id}`" v-model="f.estimated" /><Label :for="`rd-est-${id}`">{{ t('costs.readingEstimated') }}</Label></div>
      <Button type="submit" :disabled="busy">{{ t('costs.addReading') }}</Button>
    </form>
  </Panel>
</template>
