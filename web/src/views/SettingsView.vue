<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/PageHeader.vue'
import Panel from '@/components/Panel.vue'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAction } from '@/composables/useAction'
import { useTheme } from '@/composables/useTheme'
import { setLocale, type Locale } from '@/i18n'
import { api } from '@/lib/api'
import { ago } from '@/lib/format'
import type { Run } from '@/lib/types'

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
</script>

<template>
  <PageHeader :title="t('settings.title')" />
  <div class="flex max-w-3xl flex-col gap-4">
    <Panel :title="t('settings.appearance')">
      <div class="flex flex-wrap items-center gap-6">
        <div class="grid gap-1.5">
          <p class="text-sm text-muted-foreground">{{ t('app.theme') }}</p>
          <Tabs v-model="mode"><TabsList>
            <TabsTrigger value="light">{{ t('app.themes.light') }}</TabsTrigger>
            <TabsTrigger value="dark">{{ t('app.themes.dark') }}</TabsTrigger>
            <TabsTrigger value="auto">{{ t('app.themes.auto') }}</TabsTrigger>
          </TabsList></Tabs>
        </div>
        <div class="grid gap-1.5">
          <p class="text-sm text-muted-foreground">{{ t('app.language') }}</p>
          <Tabs :model-value="locale" @update:model-value="(v) => setLocale(v as Locale)"><TabsList>
            <TabsTrigger value="de">Deutsch</TabsTrigger>
            <TabsTrigger value="en">English</TabsTrigger>
          </TabsList></Tabs>
        </div>
      </div>
    </Panel>

    <Panel :title="t('settings.collector')">
      <template #actions>
        <Button type="button" size="sm" :disabled="busy" @click="collect">{{ busy ? t('settings.collecting') : t('settings.collectNow') }}</Button>
      </template>
      <p v-if="lastStatus" class="mb-3 text-sm" :class="statusTone(lastStatus)">{{ t('settings.collected', { status: t(`settings.status.${lastStatus}`) }) }}</p>
      <h3 class="mb-1 text-sm font-medium text-muted-foreground">{{ t('settings.runs') }}</h3>
      <ul class="divide-y divide-border text-sm">
        <li v-for="r in runs.data.value ?? []" :key="r.id" class="py-2">
          <div class="flex flex-wrap items-baseline gap-x-3">
            <span class="w-40 tabular">{{ ago(r.started_at) }}</span>
            <span class="font-medium" :class="statusTone(r.status)">{{ r.status ? t(`settings.status.${r.status}`) : t('common.loading') }}</span>
            <span class="text-caption tabular">{{ r.ok ?? 0 }} ok<template v-if="r.failed">, {{ r.failed }} {{ t('settings.status.failed') }}</template></span>
          </div>
          <pre v-if="r.message" class="mt-1 whitespace-pre-wrap font-sans text-xs text-muted-foreground">{{ r.message }}</pre>
        </li>
      </ul>
    </Panel>

    <Panel :title="t('settings.about')">
      <p class="text-sm text-muted-foreground">{{ t('settings.aboutBody') }}</p>
      <Button v-if="auth.data.value?.required" type="button" variant="outline" size="sm" class="mt-3" @click="logout">{{ t('settings.logout') }}</Button>
    </Panel>
  </div>
</template>
