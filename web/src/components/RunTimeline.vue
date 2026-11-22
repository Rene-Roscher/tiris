<script setup lang="ts">
/*
  "When did what run": one row per device over a day. Faint track = drawing any power (>= 1 W), solid bars = runs
  above the device's own threshold (API /api/events). Below: the biggest runs of the day with time, duration and cost.
*/
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { useDevices } from '@/composables/useDevices'
import { api } from '@/lib/api'
import { duration, kwh, money, NBSP, time, watts } from '@/lib/format'

interface Run { start: number; end: number; wh: number; peak_w: number }
interface Ev {
  day: string; start: number; end: number; price: number | null; covered_from: number | null
  devices: { id: string; name: string; threshold_w: number; wh: number; on_s: number; base_w: number; runs: Run[]; drawing: [number, number][] }[]
}

const props = defineProps<{ day: string }>()
const { t } = useI18n()
const { color } = useDevices()
const q = useQuery({
  queryKey: computed(() => ['events', props.day]),
  queryFn: () => api.get<Ev>(`/api/events?day=${props.day}`),
  refetchInterval: 60_000,
  placeholderData: (p) => p,
})
const ev = computed(() => q.data.value)
const span = computed(() => (ev.value ? ev.value.end - ev.value.start : 86400))
const x = (ts: number) => `${(((ts - (ev.value?.start ?? 0)) / span.value) * 100).toFixed(3)}%`
const w = (a: number, b: number) => `${Math.max(0.25, ((b - a) / span.value) * 100).toFixed(3)}%`
const rows = computed(() => (ev.value?.devices ?? []).filter((d) => d.drawing.length || d.runs.length))
const idle = computed(() => (ev.value?.devices ?? []).filter((d) => !d.drawing.length && !d.runs.length))
const nowPos = computed(() => {
  const n = Date.now() / 1000
  return ev.value && n > ev.value.start && n < ev.value.end ? x(n) : null
})
const eur = (wh: number) => (ev.value?.price != null ? money(wh / 1000 * ev.value.price) : null)
const runLabel = (name: string, r: Run) => [
  `${name}: ${time(r.start)}–${time(r.end)}`, duration(r.end - r.start), `${kwh(r.wh, 2)}${NBSP}kWh`,
  eur(r.wh), `${t('events.peak')} ${watts(r.peak_w)}`,
].filter(Boolean).join(' · ')
const top = computed(() => (ev.value?.devices ?? [])
  .flatMap((d) => d.runs.map((r) => ({ ...r, id: d.id, name: d.name })))
  .sort((a, b) => b.wh - a.wh).slice(0, 6))
const ticks = [0, 3, 6, 9, 12, 15, 18, 21]
// before the first stored minute nothing is known: shaded, not "idle"
const uncovered = computed(() => {
  const c = ev.value?.covered_from
  return ev.value && c && c - ev.value.start > 900 ? x(c) : null
})
// devices that draw power all day without a single run above their threshold (base load, always-on)
const steady = (d: Ev['devices'][number]) => !d.runs.length && d.base_w >= 1
</script>

<template>
  <div v-if="!ev" class="h-[220px] animate-pulse rounded-md bg-muted" />
  <p v-else-if="!rows.length" class="py-8 text-center text-sm text-muted-foreground">{{ t('events.none') }}</p>
  <div v-else>
    <div class="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] gap-x-4 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)]">
      <template v-for="d in rows" :key="d.id">
        <RouterLink :to="`/devices/${d.id}`" class="flex h-8 min-w-0 items-center gap-2 text-sm hover:underline">
          <span class="size-2.5 shrink-0 rounded-sm" :style="{ background: color(d.id) }" aria-hidden="true" />
          <span class="truncate font-medium" :title="d.name">{{ d.name }}</span>
          <span class="flex-1" aria-hidden="true" />
          <span class="hidden shrink-0 text-xs text-caption tabular sm:inline">{{ kwh(d.wh, 2) }}{{ NBSP }}kWh</span>
        </RouterLink>
        <div class="relative h-8" role="list" :aria-label="d.name">
          <div class="absolute inset-x-0 top-1/2 h-px bg-border" aria-hidden="true" />
          <span v-if="uncovered" class="absolute inset-y-1 left-0 rounded-sm bg-muted" :style="{ width: uncovered }" aria-hidden="true" />
          <span v-if="nowPos" class="absolute inset-y-1 w-px bg-primary" :style="{ left: nowPos }" aria-hidden="true" />
          <span v-for="(s, i) in d.drawing" :key="`d${i}`" class="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full opacity-35"
                :style="{ left: x(s[0]), width: w(s[0], s[1]), background: color(d.id) }" aria-hidden="true" />
          <span v-for="(r, i) in d.runs" :key="`r${i}`" role="listitem" tabindex="0" :title="runLabel(d.name, r)" :aria-label="runLabel(d.name, r)"
                class="absolute top-1/2 h-4 -translate-y-1/2 rounded-sm outline-offset-2 transition-[filter] hover:brightness-125"
                :style="{ left: x(r.start), width: w(r.start, r.end), background: color(d.id) }" />
        </div>
      </template>
      <div aria-hidden="true" />
      <div class="relative mt-1 h-5 text-xs text-caption" aria-hidden="true">
        <span v-for="h in ticks" :key="h" class="absolute -translate-x-1/2 tabular first:translate-x-0" :class="h % 6 ? 'hidden sm:inline' : ''" :style="{ left: `${(h / 24) * 100}%` }">{{ h }}</span>
      </div>
    </div>
    <p v-if="uncovered && ev.covered_from" class="mt-3 text-sm text-caption">
      <span class="mr-1.5 inline-block size-2.5 rounded-sm bg-muted align-[-1px]" aria-hidden="true" />{{ t('events.uncovered', { time: time(ev.covered_from) }) }}
    </p>
    <p v-if="rows.some(steady)" class="mt-1 text-sm text-caption">{{ t('events.steady', { list: rows.filter(steady).map((d) => `${d.name} ~${watts(d.base_w)}`).join(', ') }) }}</p>
    <p v-if="idle.length" class="mt-1 text-sm text-caption">{{ t('events.idle', { names: idle.map((d) => d.name).join(', ') }) }}</p>

    <div v-if="top.length" class="mt-6">
      <h3 class="mb-1 text-xs font-medium text-caption">{{ t('events.biggest') }}</h3>
      <ul class="divide-y divide-border border-y border-border text-sm">
        <li v-for="r in top" :key="`${r.id}-${r.start}`" class="grid h-10 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-4 sm:grid-cols-[minmax(0,1fr)_7rem_5rem_5rem_4.5rem]">
          <span class="flex min-w-0 items-center gap-2.5">
            <span class="size-2.5 shrink-0 rounded-sm" :style="{ background: color(r.id) }" aria-hidden="true" />
            <span class="truncate font-medium">{{ r.name }}</span>
          </span>
          <span class="text-muted-foreground tabular">{{ time(r.start) }}–{{ time(r.end) }}</span>
          <span class="hidden text-right text-muted-foreground tabular sm:inline">{{ duration(r.end - r.start) }}</span>
          <span class="text-right tabular">{{ kwh(r.wh, 2) }}{{ NBSP }}kWh</span>
          <span class="hidden text-right tabular sm:inline">{{ eur(r.wh) ?? '' }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>
