<script setup lang="ts">
import { CircleAlert, CircleCheck, Info } from '@lucide/vue'

defineProps<{ tone: 'success' | 'error' | 'info'; title: string; description?: string }>()
</script>

<template>
  <div
    class="flex w-[min(360px,calc(100vw-32px))] items-start gap-2.5 rounded-lg border border-border bg-popover px-3.5 py-3 text-popover-foreground shadow-float"
    :role="tone === 'error' ? 'alert' : 'status'"
  >
    <CircleCheck v-if="tone === 'success'" class="mt-px size-4 shrink-0 text-good" aria-hidden="true" />
    <CircleAlert v-else-if="tone === 'error'" class="mt-px size-4 shrink-0 text-bad" aria-hidden="true" />
    <Info v-else class="mt-px size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
    <div class="min-w-0">
      <p class="font-medium">{{ title }}</p>
      <p v-if="description" class="mt-0.5 text-sm text-muted-foreground">{{ description }}</p>
    </div>
  </div>
</template>
