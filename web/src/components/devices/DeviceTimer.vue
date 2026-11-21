<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAction } from '@/composables/useAction'
import { api } from '@/lib/api'
import type { Device } from '@/lib/types'

const props = defineProps<{ device: Device }>()
const { t } = useI18n()
const { busy, run } = useAction([['devices']], () => props.device.name)
const minutes = ref(30)
const action = ref<'on' | 'off'>(props.device.protected ? 'on' : 'off')
const start = () => run(() => api.post(`/api/devices/${props.device.id}/timer`, { minutes: Number(minutes.value), on: action.value === 'on' }), t('devices.timer.set'))
const clear = () => run(() => api.del(`/api/devices/${props.device.id}/timer`), t('devices.timer.cleared'))
const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
</script>

<template>
  <div class="flex flex-col gap-4">
    <div v-if="device.status.timer" class="flex flex-wrap items-center gap-3 text-sm">
      <span>{{ t('devices.timer.active', { action: t(device.status.timer.on ? 'devices.timer.turnOn' : 'devices.timer.turnOff'), left: fmt(device.status.timer.remaining_s) }) }}</span>
      <Button type="button" variant="outline" size="sm" :disabled="busy" @click="clear">{{ t('devices.timer.clear') }}</Button>
    </div>
    <form class="flex flex-wrap items-end gap-3" @submit.prevent="start">
      <div class="grid gap-1.5"><Label :for="`${device.id}-min`">{{ t('devices.timer.in') }}</Label>
        <div class="flex items-center gap-2"><Input :id="`${device.id}-min`" v-model="minutes" type="number" min="1" max="1440" class="w-24 tabular" />
          <span class="text-sm text-muted-foreground">{{ t('devices.timer.minutes') }}</span></div></div>
      <div class="flex gap-1">
        <Button v-for="m in [15, 30, 60, 120]" :key="m" type="button" variant="outline" size="sm" @click="minutes = m">{{ m < 60 ? `${m} min` : `${m / 60} h` }}</Button>
      </div>
      <div class="grid gap-1.5"><Label>{{ t('devices.timer.then') }}</Label>
        <Select v-model="action"><SelectTrigger class="w-40"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="off" :disabled="device.protected">{{ t('devices.timer.turnOff') }}</SelectItem>
            <SelectItem value="on">{{ t('devices.timer.turnOn') }}</SelectItem></SelectContent></Select></div>
      <Button type="submit" :disabled="busy || (device.protected && action === 'off')">{{ t('devices.timer.start') }}</Button>
    </form>
    <p class="text-sm text-caption">{{ t('devices.timer.hint') }}</p>
  </div>
</template>
