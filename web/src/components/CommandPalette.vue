<script setup lang="ts">
/*
  Command palette (Ctrl/Cmd+K): jump to a page or device, switch a device, fetch now, change theme or language.
  Keyboard: arrows move, Enter runs, Escape closes. The list is a listbox driven by aria-activedescendant.
*/
import { Activity, ArrowRight, Download, LayoutDashboard, Languages, Moon, Plug, Power, Search, Settings, Sun, SunMoon, Wallet } from '@lucide/vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useEventListener } from '@vueuse/core'
import { type Component, computed, nextTick, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { confirm } from '@/composables/useConfirm'
import { useDevices } from '@/composables/useDevices'
import { useLive } from '@/composables/useLive'
import { useTheme } from '@/composables/useTheme'
import { setLocale } from '@/i18n'
import { api } from '@/lib/api'
import { watts } from '@/lib/format'
import { notify } from '@/lib/toast'

const open = defineModel<boolean>('open', { default: false })
const { t, locale } = useI18n()
const router = useRouter()
const qc = useQueryClient()
const { list, color } = useDevices()
const { snapshot } = useLive()
const { mode } = useTheme()
const id = useId()

interface Item { id: string; group: string; label: string; hint?: string; icon?: Component; swatch?: string; keywords?: string; run: () => void | Promise<void> }

const go = (to: string) => () => { router.push(to) }
async function power(devId: string, name: string, on: boolean) {
  if (!on) {
    const ok = await confirm({ title: t('devices.confirmOffTitle', { name }), body: t('devices.confirmOffBody'), action: t('devices.off'), danger: true })
    if (!ok) return
  }
  try {
    await api.post(`/api/devices/${devId}/power`, { on })
    notify.success(t(on ? 'devices.switchedOn' : 'devices.switchedOff', { name }))
    await qc.invalidateQueries({ queryKey: ['devices'] })
  } catch (e) { notify.error(name, (e as Error).message) }
}
async function collect() {
  const h = notify.loading(t('settings.collecting'))
  try {
    const r = await api.post<{ status: string }>('/api/collect')
    h.update({ type: r.status === 'ok' ? 'success' : 'warning', title: t('settings.collected', { status: t(`settings.status.${r.status}`) }) })
    await qc.invalidateQueries()
  } catch (e) { h.update({ type: 'error', title: t('settings.collector'), description: (e as Error).message }) }
}

const items = computed<Item[]>(() => {
  const g = { pages: t('palette.pages'), devices: t('palette.devices'), switch: t('palette.switch'), actions: t('palette.actions') }
  const live = snapshot.value?.devices ?? {}
  return [
    { id: 'p-overview', group: g.pages, label: t('nav.overview'), icon: LayoutDashboard, run: go('/') },
    { id: 'p-live', group: g.pages, label: t('nav.live'), icon: Activity, run: go('/live') },
    { id: 'p-devices', group: g.pages, label: t('nav.devices'), icon: Plug, run: go('/devices') },
    { id: 'p-costs', group: g.pages, label: t('nav.costs'), icon: Wallet, run: go('/costs') },
    { id: 'p-settings', group: g.pages, label: t('nav.settings'), icon: Settings, run: go('/settings') },
    ...list.value.map((d) => ({
      id: `d-${d.id}`, group: g.devices, label: d.name, swatch: color(d.id), keywords: [d.room, d.category, d.model].filter(Boolean).join(' '),
      hint: d.status.device_on === false ? t('app.off') : live[d.id] ? watts(live[d.id]!.w) : undefined, run: go(`/devices/${d.id}`),
    })),
    ...list.value.filter((d) => d.status.reachable && !(d.protected && d.status.device_on)).map((d) => {
      const on = !!d.status.device_on
      return { id: `s-${d.id}`, group: g.switch, label: t(on ? 'palette.turnOff' : 'palette.turnOn', { name: d.name }), icon: Power,
        keywords: `${d.name} ${on ? 'aus off' : 'an on ein'}`, run: () => power(d.id, d.name, !on) }
    }),
    { id: 'a-collect', group: g.actions, label: t('settings.collectNow'), icon: Download, run: collect },
    { id: 'a-light', group: g.actions, label: `${t('app.theme')}: ${t('app.themes.light')}`, icon: Sun, run: () => { mode.value = 'light' } },
    { id: 'a-dark', group: g.actions, label: `${t('app.theme')}: ${t('app.themes.dark')}`, icon: Moon, run: () => { mode.value = 'dark' } },
    { id: 'a-auto', group: g.actions, label: `${t('app.theme')}: ${t('app.themes.auto')}`, icon: SunMoon, run: () => { mode.value = 'auto' } },
    { id: 'a-lang', group: g.actions, label: locale.value === 'de' ? 'Language: English' : 'Sprache: Deutsch', icon: Languages,
      run: () => setLocale(locale.value === 'de' ? 'en' : 'de') },
  ]
})

// match every word of the query against label + keywords (case and umlaut insensitive)
const norm = (s: string) => s.toLocaleLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '')
const query = ref('')
const results = computed(() => {
  const words = norm(query.value).split(/\s+/).filter(Boolean)
  const all = items.value.filter((i) => !words.length || words.every((w) => norm(`${i.label} ${i.keywords ?? ''} ${i.group}`).includes(w)))
  // without a query, switching every device would flood the list: show it only when searched for
  return words.length ? all : all.filter((i) => !i.id.startsWith('s-'))
})
const groups = computed(() => {
  const m = new Map<string, Item[]>()
  for (const i of results.value) m.set(i.group, [...(m.get(i.group) ?? []), i])
  return [...m.entries()]
})
const active = ref(0)
watch(query, () => { active.value = 0 })
watch(open, (o) => { if (o) { query.value = ''; active.value = 0 } })
const optId = (i: number) => `${id}-opt-${i}`
function move(d: number) {
  const n = results.value.length
  if (!n) return
  active.value = (active.value + d + n) % n
  nextTick(() => document.getElementById(optId(active.value))?.scrollIntoView({ block: 'nearest' }))
}
async function runItem(i: Item | undefined) {
  if (!i) return
  open.value = false
  await nextTick()
  await i.run()
}

// a plain keydown listener: key-state trackers can miss the keyup when focus moves into the dialog
useEventListener(window, 'keydown', (e: KeyboardEvent) => {
  if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    open.value = !open.value
  }
})
const indexOf = (it: Item) => results.value.indexOf(it)
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="top-[18%] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-xl" :show-close-button="false">
      <DialogTitle class="sr-only">{{ t('palette.title') }}</DialogTitle>
      <DialogDescription class="sr-only">{{ t('palette.hint') }}</DialogDescription>
      <div class="flex items-center gap-2.5 border-b border-border px-4">
        <Search class="size-4 shrink-0 text-caption" aria-hidden="true" />
        <input v-model="query" type="text" role="combobox" aria-expanded="true" :aria-controls="`${id}-list`"
               :aria-activedescendant="results.length ? optId(active) : undefined" :placeholder="t('palette.placeholder')"
               class="h-12 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-caption"
               @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" @keydown.enter.prevent="runItem(results[active])" />
        <kbd class="rounded-sm border border-border px-1.5 text-xs text-caption">Esc</kbd>
      </div>
      <div :id="`${id}-list`" role="listbox" :aria-label="t('palette.title')" class="max-h-[min(60vh,420px)] overflow-y-auto p-2">
        <p v-if="!results.length" class="px-3 py-8 text-center text-sm text-muted-foreground">{{ t('palette.empty') }}</p>
        <template v-for="[g, its] in groups" :key="g">
          <p class="px-2.5 pb-1 pt-2 text-xs font-medium text-caption" aria-hidden="true">{{ g }}</p>
          <div v-for="it in its" :id="optId(indexOf(it))" :key="it.id" role="option" :aria-selected="indexOf(it) === active"
               class="flex h-9 cursor-pointer items-center gap-2.5 rounded-md px-2.5 text-sm"
               :class="indexOf(it) === active ? 'bg-muted text-foreground' : 'text-muted-foreground'"
               @mousemove="active = indexOf(it)" @click="runItem(it)">
            <span v-if="it.swatch" class="mx-[3px] size-2.5 shrink-0 rounded-sm" :style="{ background: it.swatch }" aria-hidden="true" />
            <component :is="it.icon" v-else-if="it.icon" class="size-4 shrink-0" aria-hidden="true" />
            <span class="truncate">{{ it.label }}</span>
            <span class="flex-1" aria-hidden="true" />
            <span v-if="it.hint" class="shrink-0 text-xs text-caption tabular">{{ it.hint }}</span>
            <ArrowRight v-if="indexOf(it) === active" class="size-3.5 shrink-0 text-caption" aria-hidden="true" />
          </div>
        </template>
      </div>
      <p class="border-t border-border bg-muted/50 px-4 py-2 text-xs text-caption">{{ t('palette.hint') }}</p>
    </DialogContent>
  </Dialog>
</template>
