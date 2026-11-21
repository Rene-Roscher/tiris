<script setup lang="ts">
/** 30-point trend line in the de-emphasis colour, the latest point in the accent. */
import { computed } from 'vue'

const props = withDefaults(defineProps<{ values: number[]; width?: number; height?: number }>(), { width: 96, height: 24 })
const d = computed(() => {
  const v = props.values, n = v.length, max = Math.max(1, ...v)
  if (n < 2) return null
  const x = (i: number) => 2 + (i * (props.width - 6)) / (n - 1)
  const y = (val: number) => props.height - 3 - (val / max) * (props.height - 6)
  const pts = v.map((val, i) => `${x(i).toFixed(1)},${y(val).toFixed(1)}`)
  return { line: `M${pts.join('L')}`, last: { x: x(n - 1), y: y(v[n - 1]!) } }
})
</script>

<template>
  <svg :width="width" :height="height" aria-hidden="true" class="overflow-visible">
    <template v-if="d">
      <path :d="d.line" fill="none" stroke="var(--caption)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" />
      <circle :cx="d.last.x" :cy="d.last.y" r="2.5" fill="var(--primary)" />
    </template>
  </svg>
</template>
