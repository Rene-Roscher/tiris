<script setup lang="ts">
/** A page section without a box: title, optional summary on the right, content. Parents separate sections with hairlines. */
defineProps<{ title?: string; summary?: string }>()
</script>

<template>
  <section class="min-w-0 py-8">
    <header v-if="title || summary || $slots.actions" class="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <h2 v-if="title" class="font-semibold">{{ title }}</h2>
      <div class="flex items-center gap-3">
        <p v-if="summary" class="text-sm text-caption tabular">{{ summary }}</p>
        <slot name="actions" />
      </div>
    </header>
    <slot />
  </section>
</template>
