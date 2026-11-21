<script setup lang="ts">
/** label · value · delta (share; positive = more consumption = worse) · sub line. */
import { ArrowDownRight, ArrowUpRight, Minus } from '@lucide/vue'
import { computed } from 'vue'
import { pct } from '@/lib/format'

const props = defineProps<{ label: string; value: string; unit?: string; delta?: number | null; deltaLabel?: string; sub?: string; loading?: boolean }>()
const dir = computed(() => (props.delta == null || !Number.isFinite(props.delta) ? null : props.delta > 0.005 ? 'up' : props.delta < -0.005 ? 'down' : 'flat'))
</script>

<template>
  <div class="flex min-w-0 flex-col gap-1 rounded-lg border border-border bg-card px-4 py-3.5">
    <p class="text-sm text-muted-foreground">{{ label }}</p>
    <div v-if="loading" class="h-8 w-28 animate-pulse rounded-md bg-muted" />
    <p v-else class="text-2xl font-semibold">
      {{ value }}<span v-if="unit" class="ml-1 text-md font-medium tracking-normal text-muted-foreground">{{ unit }}</span>
    </p>
    <p v-if="dir && !loading" class="flex flex-wrap items-center gap-x-1 text-sm" :class="dir === 'up' ? 'text-bad' : dir === 'down' ? 'text-good' : 'text-muted-foreground'">
      <ArrowUpRight v-if="dir === 'up'" class="size-3.5" aria-hidden="true" />
      <ArrowDownRight v-else-if="dir === 'down'" class="size-3.5" aria-hidden="true" />
      <Minus v-else class="size-3.5" aria-hidden="true" />
      <span class="tabular font-medium">{{ (delta! > 0 ? '+' : '') + pct(delta) }}</span>
      <span class="text-caption">{{ deltaLabel }}</span>
    </p>
    <p v-if="sub && !loading" class="line-clamp-2 text-sm text-caption">{{ sub }}</p>
  </div>
</template>
