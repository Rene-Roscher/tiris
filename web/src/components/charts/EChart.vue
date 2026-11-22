<script setup lang="ts">
/** vue-echarts with autoresize, a fixed height and an accessible label. Options are built by the caller.
    Exposes highlight/downplay so a legend outside the chart can point at a series. */
import type { EChartsOption } from 'echarts'
import { ref } from 'vue'
import VChart from 'vue-echarts'
import '@/lib/charts'   // registers the ECharts parts once, inside the lazy chart chunk

defineProps<{ option: EChartsOption; height?: number; label: string }>()
const chart = ref<InstanceType<typeof VChart> | null>(null)
defineExpose({
  highlight: (seriesName: string) => chart.value?.dispatchAction({ type: 'highlight', seriesName }),
  downplay: (seriesName: string) => chart.value?.dispatchAction({ type: 'downplay', seriesName }),
})
</script>

<template>
  <div :style="{ height: `${height ?? 260}px` }" class="w-full" role="img" :aria-label="label">
    <VChart ref="chart" :option="option" autoresize class="size-full" />
  </div>
</template>
