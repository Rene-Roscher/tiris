<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Segmented from '@/components/Segmented.vue'
import Panel from '@/components/Panel.vue'
import { Button } from '@/components/ui/button'
import { useAction } from '@/composables/useAction'
import { useTheme } from '@/composables/useTheme'
import { setLocale, type Locale } from '@/i18n'
import { api } from '@/lib/api'
import { ago } from '@/lib/format'
import { groupRun, parseRun } from '@/lib/runs'
import type { Device, Run } from '@/lib/types'

const { t, locale } = useI18n()
const { mode } = useTheme()
const runs = useQuery({ queryKey: ['runs', 20], queryFn: () => api.get<Run[]>('/api/runs?limit=20'), refetchInterval: 30_000 })
const auth = useQuery({ queryKey: ['auth'], queryFn: () => api.get<{ required: boolean; authenticated: boolean }>('/api/auth/status') })
const { busy, run } = useAction([['runs'], ['overview'], ['devices']], () => t('settings.collector'))
async function collect() {
  const r = await run(() => api.post<{ status: string }>('/api/collect'))
  if (r) runs.refetch()
}
const logout = async () => { await api.post('/api/auth/logout'); window.location.reload() }
const statusTone = (s: string | null) => (s === 'ok' ? 'text-good' : s === 'partial' ? 'text-warn' : s ? 'text-bad' : 'text-caption')
const lastStatus = computed(() => runs.data.value?.[0]?.status)
const themeOptions = computed(() => [{ value: 'light', label: t('app.themes.light') }, { value: 'dark', label: t('app.themes.dark') }, { value: 'auto', label: t('app.themes.auto') }])
const langOptions = [{ value: 'de', label: 'Deutsch' }, { value: 'en', label: 'English' }]
const devs = useQuery({ queryKey: ['devices'], queryFn: () => api.get<{ devices: Device[] }>('/api/devices'), staleTime: 30_000 })
const nameByIp = computed(() => Object.fromEntries((devs.data.value?.devices ?? []).filter((d) => d.ip).map((d) => [d.ip!, d.name])))
const explain = (msg: string | null) => groupRun(parseRun(msg), nameByIp.value)
</script>

<template>
  <div class="mb-7 flex h-9 items-center"><h1 class="font-semibold">{{ t('settings.title') }}</h1></div>
  <div class="flex max-w-3xl flex-col divide-y divide-border">
    <section class="flex flex-wrap items-center gap-x-10 gap-y-4 pb-8">
      <div class="grid gap-2">
        <p class="text-xs font-medium text-caption">{{ t('app.theme') }}</p>
        <Segmented v-model="mode" :options="themeOptions" :label="t('app.theme')" />
      </div>
      <div class="grid gap-2">
        <p class="text-xs font-medium text-caption">{{ t('app.language') }}</p>
        <Segmented :model-value="locale" :options="langOptions" :label="t('app.language')" @update:model-value="(v) => setLocale(v as Locale)" />
      </div>
    </section>

    <Panel :title="t('settings.collector')" :description="lastStatus ? t('settings.collected', { status: t(`settings.status.${lastStatus}`) }) : undefined">
      <template #actions>
        <Button type="button" variant="outline" size="sm" :disabled="busy" @click="collect">{{ busy ? t('settings.collecting') : t('settings.collectNow') }}</Button>
      </template>
      <ul class="divide-y divide-border border-y border-border text-sm">
        <li v-for="r in runs.data.value ?? []" :key="r.id" class="grid gap-x-3 py-2.5 sm:grid-cols-[9rem_minmax(0,1fr)]">
          <span class="text-muted-foreground tabular">{{ ago(r.started_at) }}</span>
          <div class="flex flex-wrap items-baseline gap-x-3">
            <span class="font-medium" :class="statusTone(r.status)">{{ r.status ? t(`settings.status.${r.status}`) : t('common.loading') }}</span>
            <span class="text-caption tabular">{{ t('settings.plugsOk', { n: r.ok ?? 0 }) }}<template v-if="r.failed">, {{ t('settings.plugsFailed', { n: r.failed }) }}</template></span>
          </div>
          <template v-if="r.message">
            <ul class="mt-1.5 grid gap-1 text-sm text-muted-foreground sm:col-start-2">
              <li v-for="(g, i) in explain(r.message)" :key="i" class="flex gap-2">
                <span class="flex h-5 shrink-0 items-center" aria-hidden="true"><span class="size-1.5 rounded-full" :class="g.kind === 'session' || g.kind === 'misdated' || g.kind === 'discovery' ? 'bg-border-strong' : 'bg-warn-fill'" /></span>
                <span v-if="g.kind === 'other'" class="break-all font-mono text-xs">{{ g.raw[0] }}</span>
                <span v-else>{{ t(`settings.run.${g.kind}`, { names: g.names.join(', '), n: g.names.length }) }}</span>
              </li>
            </ul>
            <details class="mt-1 sm:col-start-2">
              <summary class="cursor-pointer text-xs text-caption hover:text-foreground">{{ t('settings.rawDetails') }}</summary>
              <pre class="mt-1 whitespace-pre-wrap break-all font-mono text-xs text-caption">{{ r.message }}</pre>
            </details>
          </template>
        </li>
      </ul>
    </Panel>

    <Panel :title="t('settings.about')">
      <p class="text-sm text-muted-foreground">{{ t('settings.aboutBody') }}</p>
      <Button v-if="auth.data.value?.required" type="button" variant="outline" size="sm" class="mt-3" @click="logout">{{ t('settings.logout') }}</Button>
    </Panel>
  </div>
</template>
