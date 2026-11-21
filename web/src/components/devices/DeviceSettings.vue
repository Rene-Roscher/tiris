<script setup lang="ts">
import { reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { confirm } from '@/composables/useConfirm'
import { useAction } from '@/composables/useAction'
import { api } from '@/lib/api'
import type { Device } from '@/lib/types'

const props = defineProps<{ device: Device; rooms: string[]; categories: string[] }>()
const { t } = useI18n()
const { busy, run } = useAction([['devices'], ['overview']], () => props.device.name)
const form = reactive({ room: '', category: '', note: '', protected: false })
watch(() => props.device, (d) => Object.assign(form, { room: d.room ?? '', category: d.category ?? '', note: d.note ?? '', protected: d.protected }), { immediate: true })
const id = (k: string) => `${props.device.id}-${k}`

const save = () => run(() => api.patch(`/api/devices/${props.device.id}`, form), t('common.saved'))
async function archive() {
  const ok = await confirm({ title: t('devices.maintenance.archiveTitle', { name: props.device.name }), body: t('devices.maintenance.archiveBody'),
    action: t('devices.maintenance.archive') })
  if (ok) await run(() => api.patch(`/api/devices/${props.device.id}`, { retired: true }), t('devices.maintenance.archived'))
}
</script>

<template>
  <form class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" @submit.prevent="save">
    <div class="grid gap-1.5"><Label :for="id('room')">{{ t('devices.room') }}</Label>
      <Input :id="id('room')" v-model="form.room" list="tiris-rooms" maxlength="60" /></div>
    <div class="grid gap-1.5"><Label :for="id('cat')">{{ t('devices.category') }}</Label>
      <Input :id="id('cat')" v-model="form.category" list="tiris-categories" maxlength="60" /></div>
    <div class="grid gap-1.5 sm:col-span-2"><Label :for="id('note')">{{ t('devices.note') }}</Label>
      <Input :id="id('note')" v-model="form.note" maxlength="500" /></div>
    <div class="flex items-start gap-3 sm:col-span-2 lg:col-span-3">
      <Switch :id="id('prot')" v-model="form.protected" />
      <div><Label :for="id('prot')">{{ t('devices.protected') }}</Label>
        <p class="mt-0.5 text-sm text-muted-foreground">{{ t('devices.protectedHint') }}</p></div>
    </div>
    <div class="flex items-end justify-end gap-2">
      <Button type="button" variant="ghost" :disabled="busy" @click="archive">{{ t('devices.maintenance.archive') }}</Button>
      <Button type="submit" :disabled="busy">{{ busy ? t('common.saving') : t('common.save') }}</Button>
    </div>
    <p class="text-sm text-caption sm:col-span-2 lg:col-span-4">{{ t('devices.localHint') }}</p>
    <datalist id="tiris-rooms"><option v-for="r in rooms" :key="r" :value="r" /></datalist>
    <datalist id="tiris-categories"><option v-for="c in categories" :key="c" :value="c" /></datalist>
  </form>
</template>
