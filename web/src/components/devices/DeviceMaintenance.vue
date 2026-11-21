<script setup lang="ts">
import { CircleCheck, CircleAlert } from '@lucide/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { confirm } from '@/composables/useConfirm'
import { useAction } from '@/composables/useAction'
import { api } from '@/lib/api'
import { dateMedium } from '@/lib/format'
import type { Device } from '@/lib/types'

const props = defineProps<{ device: Device }>()
const { t } = useI18n()
const { busy, run } = useAction([['devices']], () => props.device.name)
const s = computed(() => props.device.status)
const fw = computed(() => props.device.firmware)
const issues = computed(() => (['overcurrent', 'overheat', 'power_protection'] as const).filter((k) => s.value[k] && s.value[k] !== 'normal'))

async function reboot() {
  if (await confirm({ title: t('devices.maintenance.rebootTitle', { name: props.device.name }), body: t('devices.maintenance.rebootBody'),
    action: t('devices.maintenance.reboot'), danger: true }))
    await run(() => api.post(`/api/devices/${props.device.id}/reboot`), t('devices.maintenance.rebooted'))
}
async function update() {
  if (await confirm({ title: t('devices.maintenance.installTitle', { version: fw.value?.version ?? '' }), body: t('devices.maintenance.installBody'),
    detail: fw.value?.notes, action: t('devices.maintenance.install'), danger: true }))
    await run(() => api.post(`/api/devices/${props.device.id}/firmware`), t('devices.maintenance.installed'))
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <dl class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm md:grid-cols-4">
      <div><dt class="text-caption">{{ t('devices.maintenance.ip') }}</dt><dd class="tabular">{{ device.ip ?? '–' }}</dd></div>
      <div><dt class="text-caption">{{ t('devices.maintenance.mac') }}</dt><dd class="tabular">{{ device.mac ?? '–' }}</dd></div>
      <div><dt class="text-caption">{{ t('devices.maintenance.firmware') }}</dt><dd>{{ s.fw_ver ?? '–' }}</dd></div>
      <div><dt class="text-caption">{{ t('devices.maintenance.hardware') }}</dt><dd>{{ device.hw_ver ?? '–' }}</dd></div>
      <div><dt class="text-caption">{{ t('devices.maintenance.wifi') }}</dt><dd class="tabular">{{ s.rssi != null ? `${s.rssi} dBm` : '–' }}</dd></div>
      <div><dt class="text-caption">{{ t('devices.maintenance.afterOutage') }}</dt>
        <dd>{{ s.default_state === 'last_states' ? t('devices.maintenance.lastState') : s.default_state ?? '–' }}</dd></div>
      <div><dt class="text-caption">{{ t('devices.maintenance.health') }}</dt>
        <dd :class="issues.length ? 'text-bad' : ''">{{ issues.length ? issues.map((k) => t(`devices.health.${k}`)).join(', ') : t('devices.maintenance.healthOk') }}</dd></div>
      <div><dt class="text-caption">{{ t('devices.maintenance.since') }}</dt><dd>{{ device.first_seen ? dateMedium(device.first_seen) : '–' }}</dd></div>
    </dl>

    <div class="flex flex-col items-start gap-2 border-t border-border pt-4">
      <template v-if="fw?.available">
        <p class="flex items-center gap-2 font-medium"><CircleAlert class="size-4 text-warn" aria-hidden="true" />
          {{ t('devices.maintenance.fwAvailable', { version: fw.version }) }}<span v-if="fw.release_date" class="font-normal text-caption">{{ fw.release_date }}</span></p>
        <pre v-if="fw.notes" class="max-w-2xl whitespace-pre-wrap rounded-md bg-muted px-3 py-2 font-sans text-sm text-muted-foreground">{{ fw.notes }}</pre>
        <Button type="button" :disabled="busy || device.protected" @click="update">{{ t('devices.maintenance.install') }}</Button>
        <p v-if="device.protected" class="text-sm text-caption">{{ t('devices.maintenance.protectedBlocks') }}</p>
      </template>
      <p v-else-if="fw?.available === false" class="flex items-center gap-2"><CircleCheck class="size-4 text-good" aria-hidden="true" />{{ t('devices.maintenance.fwCurrent') }}</p>
      <p v-else-if="fw?.pending || !fw" class="text-sm text-muted-foreground">{{ t('devices.maintenance.fwChecking') }}</p>
      <p v-else class="text-sm text-muted-foreground">{{ fw.error === 'unreachable' ? t('devices.maintenance.fwUnreachable') : t('devices.maintenance.fwFailed') }}</p>
    </div>

    <div class="flex flex-wrap items-center gap-3 border-t border-border pt-4">
      <Button type="button" variant="outline" :disabled="busy || device.protected || !s.reachable" @click="reboot">{{ t('devices.maintenance.reboot') }}</Button>
      <p class="text-sm text-caption">{{ device.protected ? t('devices.maintenance.protectedBlocks') : t('devices.maintenance.noReset') }}</p>
    </div>
  </div>
</template>
