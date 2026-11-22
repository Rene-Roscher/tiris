<script setup lang="ts">
/** Status dot that sends out one soft ring per live sample: it shows data arriving, not decoration.
    A one-shot animation restarted by the sample time; reduced motion keeps only the dot. */
defineProps<{ beat?: number | null; on: boolean }>()
</script>

<template>
  <span :key="on ? beat ?? 0 : 'off'" class="size-1.5 shrink-0 rounded-full" :class="on ? 'live-ring bg-good-fill' : 'bg-caption'" aria-hidden="true" />
</template>
