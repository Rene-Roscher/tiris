<script setup lang="ts">
/** A titled block without a box (calm style): heading, optional description and actions, content. Parents separate blocks with hairlines. */
withDefaults(defineProps<{ title?: string; description?: string; padded?: boolean }>(), { padded: true })
</script>

<template>
  <section class="min-w-0 py-8">
    <header v-if="title || $slots.actions" class="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 v-if="title" class="font-semibold">{{ title }}</h2>
        <p v-if="description" class="mt-0.5 text-sm text-caption">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="flex items-center gap-2"><slot name="actions" /></div>
    </header>
    <slot />
  </section>
</template>
