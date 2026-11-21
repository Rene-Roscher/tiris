<script setup lang="ts">
import { Trash2 } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import { reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { confirm } from '@/composables/useConfirm'
import { useAction } from '@/composables/useAction'
import { api } from '@/lib/api'
import type { Device, ScheduleRule } from '@/lib/types'

const props = defineProps<{ device: Device }>()
const { t } = useI18n()
const key = ['schedules', props.device.id]
const q = useQuery({ queryKey: key, queryFn: () => api.get<{ rules: ScheduleRule[]; max: number }>(`/api/devices/${props.device.id}/schedules`) })
const { busy, run } = useAction([key], () => props.device.name)

// Week starts Monday in the UI; the plug's bit mask has Sunday at bit 0.
const ORDER = [1, 2, 3, 4, 5, 6, 0]
const dayName = (bit: number) => new Intl.DateTimeFormat(undefined, { weekday: 'short' }).format(new Date(2024, 0, 7 + bit))  // 2024-01-07 = Sunday
const form = reactive({ kind: 'clock' as 'clock' | 'sunrise' | 'sunset', time: '22:00', offset: 0, days: [1, 2, 3, 4, 5] as number[], on: !props.device.protected })

function daysText(bits: number | null) {
  if (!bits) return t('devices.schedules.once')
  if (bits === 127) return t('devices.schedules.daily')
  if (bits === 62) return t('devices.schedules.weekdays')
  if (bits === 65) return t('devices.schedules.weekend')
  return ORDER.filter((n) => bits & (1 << n)).map(dayName).join(', ')
}
function ruleText(r: ScheduleRule) {
  const when = r.kind === 'clock' ? `${String(r.hour).padStart(2, '0')}:${String(r.minute).padStart(2, '0')}`
    : `${t(`devices.schedules.${r.kind}`)}${r.offset_minutes ? ` ${r.offset_minutes > 0 ? '+' : ''}${r.offset_minutes} min` : ''}`
  return `${daysText(r.days)}, ${when}: ${t(r.on ? 'devices.timer.turnOn' : 'devices.timer.turnOff')}`
}
const toggleDay = (n: number) => { form.days = form.days.includes(n) ? form.days.filter((x) => x !== n) : [...form.days, n] }
async function add() {
  const [hh, mm] = form.time.split(':').map(Number)
  const body: Record<string, unknown> = { kind: form.kind, on: form.on, days: form.days.reduce((a, n) => a | (1 << n), 0) || null }
  if (form.kind === 'clock') Object.assign(body, { hour: hh, minute: mm })
  else body.offset_minutes = Number(form.offset) || 0
  await run(() => api.post(`/api/devices/${props.device.id}/schedules`, body), t('devices.schedules.added'))
}
const toggle = (r: ScheduleRule) => run(() => api.patch(`/api/devices/${props.device.id}/schedules/${r.id}`, { enabled: !r.enabled }))
async function remove(r: ScheduleRule) {
  if (await confirm({ title: t('devices.schedules.deleteTitle'), body: ruleText(r), action: t('common.delete'), danger: true }))
    await run(() => api.del(`/api/devices/${props.device.id}/schedules/${r.id}`), t('common.deleted'))
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <div v-if="q.isLoading.value" class="h-16 animate-pulse rounded-md bg-muted" />
    <p v-else-if="q.isError.value" class="text-sm text-bad">{{ q.error.value?.message }}</p>
    <template v-else-if="q.data.value">
      <ul v-if="q.data.value.rules.length" class="divide-y divide-border rounded-md border border-border">
        <li v-for="r in q.data.value.rules" :key="r.id" class="flex items-center gap-3 px-3 py-2">
          <Switch :model-value="r.enabled" :disabled="busy" :aria-label="ruleText(r)" @update:model-value="toggle(r)" />
          <span class="flex-1 text-sm" :class="r.enabled ? '' : 'text-caption'">{{ ruleText(r) }}</span>
          <Button type="button" variant="ghost" size="icon-sm" :aria-label="t('common.delete')" :disabled="busy" @click="remove(r)">
            <Trash2 class="size-4" aria-hidden="true" />
          </Button>
        </li>
      </ul>
      <p v-else class="text-sm text-muted-foreground">{{ t('devices.schedules.empty') }}</p>
      <p class="text-sm text-caption">{{ t('devices.schedules.used', { n: q.data.value.rules.length, max: q.data.value.max }) }}</p>
    </template>

    <form class="flex flex-wrap items-end gap-3 border-t border-border pt-4" @submit.prevent="add">
      <div class="grid gap-1.5"><Label>{{ t('devices.schedules.trigger') }}</Label>
        <Select v-model="form.kind"><SelectTrigger class="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="clock">{{ t('devices.schedules.clock') }}</SelectItem>
            <SelectItem value="sunrise">{{ t('devices.schedules.sunrise') }}</SelectItem>
            <SelectItem value="sunset">{{ t('devices.schedules.sunset') }}</SelectItem>
          </SelectContent></Select></div>
      <div v-if="form.kind === 'clock'" class="grid gap-1.5"><Label :for="`${device.id}-time`">{{ t('devices.schedules.clock') }}</Label>
        <Input :id="`${device.id}-time`" v-model="form.time" type="time" required class="w-32" /></div>
      <div v-else class="grid gap-1.5"><Label :for="`${device.id}-off`">{{ t('devices.schedules.offset') }}</Label>
        <Input :id="`${device.id}-off`" v-model="form.offset" type="number" min="-720" max="720" class="w-28 tabular" /></div>
      <div class="flex gap-1" role="group" :aria-label="t('devices.schedules.trigger')">
        <button v-for="n in ORDER" :key="n" type="button" :aria-pressed="form.days.includes(n)" @click="toggleDay(n)"
                class="size-9 rounded-md border text-sm transition-[background-color,color,border-color] duration-150"
                :class="form.days.includes(n) ? 'border-transparent bg-primary font-medium text-primary-foreground' : 'border-border bg-card text-muted-foreground hover:bg-accent'">
          {{ dayName(n) }}
        </button>
      </div>
      <div class="grid gap-1.5"><Label>{{ t('devices.schedules.action') }}</Label>
        <Select :model-value="form.on ? 'on' : 'off'" @update:model-value="(v) => (form.on = v === 'on')"><SelectTrigger class="w-40"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="off" :disabled="device.protected">{{ t('devices.timer.turnOff') }}</SelectItem>
            <SelectItem value="on">{{ t('devices.timer.turnOn') }}</SelectItem></SelectContent></Select></div>
      <Button type="submit" :disabled="busy || (device.protected && !form.on)">{{ t('devices.schedules.add') }}</Button>
      <p v-if="!form.days.length" class="w-full text-sm text-caption">{{ t('devices.schedules.noDays') }}</p>
    </form>
  </div>
</template>
