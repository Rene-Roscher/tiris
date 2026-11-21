<script setup lang="ts" generic="T extends string | number">
/** Quiet segmented control: text buttons, the chosen one on a subtle surface. */
defineProps<{ options: { value: T; label: string }[]; label: string }>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <div class="flex gap-0.5" role="group" :aria-label="label">
    <button v-for="o in options" :key="String(o.value)" type="button" :aria-pressed="model === o.value"
            class="h-7 rounded-md px-2.5 text-sm font-medium transition-[color,background-color]"
            :class="model === o.value ? 'bg-muted text-foreground' : 'text-caption hover:text-foreground'"
            @click="model = o.value">
      {{ o.label }}
    </button>
  </div>
</template>
