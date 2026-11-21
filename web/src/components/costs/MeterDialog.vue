<script setup lang="ts">
import { reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAction } from '@/composables/useAction'
import { api } from '@/lib/api'
import type { Meter } from '@/lib/types'

const props = defineProps<{ meter?: Meter | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [id: number] }>()
const { t } = useI18n()
const { busy, run } = useAction([['meters']], () => t('costs.meters'))
const blank = () => ({ kind: 'electricity' as Meter['kind'], name: '', number: '', unit: 'kWh' as Meter['unit'], calorific_value: '', z_number: '' })
const f = reactive(blank())
watch(open, (o) => {
  if (!o) return
  const m = props.meter
  Object.assign(f, m ? { ...m, number: m.number ?? '', calorific_value: m.calorific_value ?? '', z_number: m.z_number ?? '' } : blank())
})
watch(() => f.kind, (k) => { if (k === 'electricity') f.unit = 'kWh' })
const num = (v: unknown) => (v === '' || v == null ? null : Number(String(v).replace(',', '.')))
async function save() {
  const body = { kind: f.kind, name: f.name.trim(), number: f.number || null, unit: f.unit,
    calorific_value: f.unit === 'm3' ? num(f.calorific_value) : null, z_number: f.unit === 'm3' ? num(f.z_number) : null, archived: false }
  const r = await run(() => (props.meter ? api.put<{ ok: boolean }>(`/api/meters/${props.meter.id}`, body).then(() => ({ id: props.meter!.id }))
    : api.post<{ id: number }>('/api/meters', body)), t('common.saved'))
  if (r) { emit('saved', r.id); open.value = false }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>{{ meter ? meter.name : t('costs.addMeter') }}</DialogTitle>
        <DialogDescription>{{ t('costs.noMeterBody') }}</DialogDescription>
      </DialogHeader>
      <form id="meter-form" class="grid gap-4" @submit.prevent="save">
        <div class="grid grid-cols-2 gap-3">
          <div class="grid gap-1.5"><Label>{{ t('common.kind') }}</Label>
            <Select v-model="f.kind"><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="electricity">{{ t('costs.kind.electricity') }}</SelectItem><SelectItem value="gas">{{ t('costs.kind.gas') }}</SelectItem></SelectContent></Select></div>
          <div class="grid gap-1.5"><Label>{{ t('costs.unit') }}</Label>
            <Select v-model="f.unit" :disabled="f.kind === 'electricity'"><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="kWh">kWh</SelectItem><SelectItem value="m3">m³</SelectItem></SelectContent></Select></div>
        </div>
        <div class="grid gap-1.5"><Label for="m-name">{{ t('costs.meterName') }}</Label><Input id="m-name" v-model="f.name" required maxlength="80" /></div>
        <div class="grid gap-1.5"><Label for="m-num">{{ t('costs.meterNumber') }} <span class="font-normal text-caption">({{ t('common.optional') }})</span></Label>
          <Input id="m-num" v-model="f.number" maxlength="60" /></div>
        <div v-if="f.unit === 'm3'" class="grid grid-cols-2 gap-3">
          <div class="grid gap-1.5"><Label for="m-cv">{{ t('costs.calorific') }}</Label><Input id="m-cv" v-model="f.calorific_value" inputmode="decimal" placeholder="11,2…" /></div>
          <div class="grid gap-1.5"><Label for="m-z">{{ t('costs.zNumber') }}</Label><Input id="m-z" v-model="f.z_number" inputmode="decimal" placeholder="0,95…" /></div>
          <p class="col-span-2 text-sm text-caption">{{ t('costs.gasHint') }}</p>
        </div>
      </form>
      <DialogFooter>
        <Button type="button" variant="outline" @click="open = false">{{ t('common.cancel') }}</Button>
        <Button type="submit" form="meter-form" :disabled="busy">{{ busy ? t('common.saving') : t('common.save') }}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
