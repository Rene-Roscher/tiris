<script setup lang="ts">
/** A card surface: border, no shadow (shadows belong to floating layers). */
withDefaults(defineProps<{ title?: string; description?: string; padded?: boolean }>(), { padded: true })
</script>

<template>
  <section class="min-w-0 rounded-lg border border-border bg-card">
    <header v-if="title || $slots.actions" class="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
      <div class="min-w-0">
        <h2 v-if="title" class="font-medium">{{ title }}</h2>
        <p v-if="description" class="mt-0.5 text-sm text-muted-foreground">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="flex items-center gap-2"><slot name="actions" /></div>
    </header>
    <div :class="padded ? 'px-5 pb-5 pt-4' : ''"><slot /></div>
  </section>
</template>
