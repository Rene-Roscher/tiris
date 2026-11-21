<script setup lang="ts">
/** Live total of the last minutes: accent line over a fading area. Scaled to its own range so small changes show. */
import { computed, useId } from 'vue'

const props = withDefaults(defineProps<{ points: { t: number; w: number }[]; height?: number }>(), { height: 44 })
const id = useId()
const W = 300
const path = computed(() => {
  const p = props.points
  if (p.length < 2) return null
  const vals = p.map((x) => x.w), lo = Math.min(...vals) * 0.9, hi = Math.max(...vals) * 1.05
  const t0 = p[0]!.t, t1 = p[p.length - 1]!.t, h = props.height
  const xy = p.map((x) => [((x.t - t0) / Math.max(1, t1 - t0)) * W, h - 2 - ((x.w - lo) / Math.max(1, hi - lo)) * (h - 4)])
  const line = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x!.toFixed(1)},${y!.toFixed(1)}`).join('')
  return { line, area: `${line}L${W},${h}L0,${h}Z` }
})
</script>

<template>
  <svg :viewBox="`0 0 ${W} ${height}`" preserveAspectRatio="none" class="block w-full overflow-visible" :style="{ height: `${height}px` }" aria-hidden="true">
    <defs>
      <linearGradient :id="id" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color="var(--primary)" stop-opacity="0.22" />
        <stop offset="1" stop-color="var(--primary)" stop-opacity="0" />
      </linearGradient>
    </defs>
    <template v-if="path">
      <path :d="path.area" :fill="`url(#${id})`" />
      <path :d="path.line" fill="none" stroke="var(--primary)" stroke-width="1.5" vector-effect="non-scaling-stroke" stroke-linejoin="round" />
    </template>
  </svg>
</template>
