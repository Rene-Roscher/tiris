<script setup lang="ts">
import { ChevronRight, Lock, Pencil, SlidersHorizontal, TimerIcon, TriangleAlert } from '@lucide/vue'
import { useQueryClient } from '@tanstack/vue-query'
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { confirm } from '@/composables/useConfirm'
import { api } from '@/lib/api'
import { slotVar } from '@/lib/colors'
import { duration, watts } from '@/lib/format'
import { notify } from '@/lib/toast'
import type { Device } from '@/lib/types'
import DeviceMaintenance from './DeviceMaintenance.vue'
import DeviceSchedules from './DeviceSchedules.vue'
import DeviceSettings from './DeviceSettings.vue'
import DeviceTimer from './DeviceTimer.vue'

const props = defineProps<{ device: Device; liveW?: number; rooms: string[]; categories: string[] }>()
const { t } = useI18n()
const qc = useQueryClient()
const open = ref(false)
const tab = ref('settings')
const busy = ref(false)
const d = computed(() => props.device)
// optimistic: the switch moves at once and goes back if the plug refuses
const optimistic = ref<boolean | null>(null)
const on = computed(() => optimistic.value ?? !!d.value.status.device_on)
const reachable = computed(() => d.value.status.reachable)

async function run<T>(fn: () => Promise<T>, ok?: string) {
  busy.value = true
  try {
    const r = await fn()
    if (ok) notify.success(ok)
    await qc.invalidateQueries({ queryKey: ['devices'] })
    return r
  } catch (e) {
    notify.error(d.value.name, (e as Error).message)
  } finally {
    busy.value = false
  }
}

async function setPower(v: boolean) {
  if (busy.value) return
  if (!v) {
    const load = (props.liveW ?? 0) > 5 ? ` ${t('devices.confirmOffLoad', { watts: watts(props.liveW) })}` : ''
    const ok = await confirm({ title: t('devices.confirmOffTitle', { name: d.value.name }), body: t('devices.confirmOffBody') + load,
      action: t('devices.off'), danger: true })
    if (!ok) return
  }
  optimistic.value = v
  await run(() => api.post(`/api/devices/${d.value.id}/power`, { on: v }),
    t(v ? 'devices.switchedOn' : 'devices.switchedOff', { name: d.value.name }))
  optimistic.value = null   // the refreshed status (or the old one after an error) takes over
}

// rename inline
const editing = ref(false)
const name = ref('')
const nameInput = ref<HTMLInputElement | null>(null)
async function startEdit() {
  name.value = d.value.name
  editing.value = true
  await nextTick()
  nameInput.value?.select()
}
async function saveName() {
  if (!editing.value) return
  editing.value = false
  const n = name.value.trim()
  if (!n || n === d.value.name) return
  await run(() => api.post(`/api/devices/${d.value.id}/rename`, { name: n }), t('devices.renamed', { name: n }))
}

const signal = computed(() => {
  const r = d.value.status.rssi
  return r == null ? 0 : r >= -55 ? 4 : r >= -65 ? 3 : r >= -72 ? 2 : 1
})
const issues = computed(() => (['overcurrent', 'overheat', 'power_protection'] as const)
  .filter((k) => d.value.status[k] && d.value.status[k] !== 'normal'))
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
</script>

<template>
  <li class="group/row">
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
      <Switch :model-value="on" :disabled="!reachable || (d.protected && on)" :aria-busy="busy" :class="busy ? 'pointer-events-none' : ''"
              :aria-label="d.name" @update:model-value="(v: boolean) => setPower(v)" />
      <div class="min-w-[12rem] flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <input v-if="editing" ref="nameInput" v-model="name" maxlength="64" :aria-label="t('devices.rename')"
                 class="h-7 min-w-56 rounded-md border border-ring bg-background px-2 font-medium"
                 @keydown.enter.prevent="saveName" @keydown.esc="editing = false" @blur="saveName" />
          <template v-else>
            <span class="size-2.5 shrink-0 rounded-sm" :style="{ background: slotVar(d.slot) }" aria-hidden="true" />
            <RouterLink :to="`/devices/${d.id}`" class="font-medium hover:underline" :class="on || !reachable ? '' : 'text-muted-foreground'">{{ d.name }}</RouterLink>
            <button type="button" class="grid size-6 place-items-center rounded-md text-caption opacity-0 transition-[opacity,color,background-color] hover:bg-muted hover:text-foreground focus-visible:opacity-100 group-hover/row:opacity-100"
                    :aria-label="t('devices.renameHint')" :title="t('devices.renameHint')" @click="startEdit">
              <Pencil class="size-3.5" aria-hidden="true" />
            </button>
          </template>
          <span v-if="d.protected" class="flex items-center gap-1 text-xs text-muted-foreground" :title="t('devices.protected')">
            <Lock class="size-3" aria-hidden="true" />{{ t('devices.protected') }}
          </span>
        </div>
        <div class="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm text-caption">
          <span>{{ d.model }}</span>
          <span v-if="d.category">{{ d.category }}</span>
          <span v-if="reachable" class="flex items-end gap-px" :title="`${d.status.rssi} dBm`">
            <span v-for="n in 4" :key="n" class="w-[3px] rounded-[1px]" :class="n <= signal ? 'bg-muted-foreground' : 'bg-border-strong'"
                  :style="{ height: `${3 + n * 2.5}px` }" aria-hidden="true" />
            <span class="ml-1">{{ t(`devices.signal.${signal || 1}`) }}</span>
          </span>
          <span v-if="on && d.status.on_time_s">{{ t('devices.onSince', { duration: duration(d.status.on_time_s) }) }}</span>
          <span v-if="!reachable" class="text-bad">{{ t('devices.unreachable') }}</span>
          <span v-if="d.status.timer" class="flex items-center gap-1 font-medium text-foreground">
            <TimerIcon class="size-3.5" aria-hidden="true" />
            {{ t('devices.timer.active', { action: t(d.status.timer.on ? 'devices.timer.turnOn' : 'devices.timer.turnOff'), left: mmss(d.status.timer.remaining_s) }) }}
          </span>
          <span v-for="k in issues" :key="k" class="flex items-center gap-1 text-bad">
            <TriangleAlert class="size-3.5" aria-hidden="true" />{{ t(`devices.health.${k}`) }}
          </span>
          <button v-if="d.firmware?.available" type="button" class="flex items-center gap-1.5 rounded-sm font-medium text-warn hover:underline"
                  @click="open = true; tab = 'maintenance'">
            <span class="size-1.5 rounded-full bg-warn-fill" aria-hidden="true" />
            {{ t('devices.maintenance.fwAvailable', { version: d.firmware.version?.split(' ')[0] }) }}
          </button>
        </div>
      </div>
      <div class="flex w-full items-center justify-end gap-1 sm:w-auto">
        <p class="mr-3 w-20 text-right tabular" :class="on ? 'text-md font-semibold' : 'text-sm text-caption'">{{ on ? watts(liveW) : t('app.off') }}</p>
        <Button type="button" variant="ghost" size="icon-sm" :aria-expanded="open" :aria-label="t('devices.manage')" :title="t('devices.manage')"
                :class="open ? 'bg-muted text-foreground' : 'text-caption'" @click="open = !open">
          <SlidersHorizontal class="size-4" aria-hidden="true" />
        </Button>
        <RouterLink :to="`/devices/${d.id}`" class="grid size-8 place-items-center rounded-md text-caption transition-[color,background-color] hover:bg-muted hover:text-foreground"
                    :aria-label="t('detail.open')" :title="t('detail.open')">
          <ChevronRight class="size-4" aria-hidden="true" />
        </RouterLink>
      </div>
    </div>

    <div v-if="open" class="mb-3 rounded-lg bg-muted/60 px-4 py-4">
      <Tabs v-model="tab">
        <TabsList>
          <TabsTrigger value="settings">{{ t('devices.tabs.settings') }}</TabsTrigger>
          <TabsTrigger value="timer" :disabled="!reachable">{{ t('devices.tabs.timer') }}</TabsTrigger>
          <TabsTrigger value="schedules" :disabled="!reachable">{{ t('devices.tabs.schedules') }}</TabsTrigger>
          <TabsTrigger value="maintenance">{{ t('devices.tabs.maintenance') }}</TabsTrigger>
        </TabsList>
        <TabsContent value="settings" class="pt-4"><DeviceSettings :device="d" :rooms="rooms" :categories="categories" /></TabsContent>
        <TabsContent value="timer" class="pt-4"><DeviceTimer :device="d" /></TabsContent>
        <TabsContent value="schedules" class="pt-4"><DeviceSchedules :device="d" /></TabsContent>
        <TabsContent value="maintenance" class="pt-4"><DeviceMaintenance :device="d" /></TabsContent>
      </Tabs>
    </div>
  </li>
</template>
