<script setup lang="ts">
/** vue-echarts with autoresize, a fixed height and an accessible label. Options are built by the caller. */
import type { EChartsOption } from 'echarts'
import VChart from 'vue-echarts'
import '@/lib/charts'   // registers the ECharts parts once, inside the lazy chart chunk

defineProps<{ option: EChartsOption; height?: number; label: string }>()
</script>

<template>
  <div :style="{ height: `${height ?? 260}px` }" class="w-full" role="img" :aria-label="label">
    <VChart :option="option" autoresize class="size-full" />
  </div>
</template>
