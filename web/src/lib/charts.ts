/** ECharts: tree-shaken registration and a theme read from the design tokens (re-read on theme change). */
import { BarChart, HeatmapChart, LineChart } from 'echarts/charts'
import { AriaComponent, DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

use([CanvasRenderer, LineChart, BarChart, HeatmapChart, GridComponent, TooltipComponent, LegendComponent,
  AriaComponent, DataZoomComponent, MarkLineComponent, VisualMapComponent])

export function token(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim()
}

/** Category colours per slot (1..6); 0 = "other". Colour follows the device, never its rank in a filter. */
export const slotColor = (slot: number) => token(slot >= 1 && slot <= 6 ? `chart-${slot}` : 'chart-other')

export function baseOption() {
  const text = token('muted-foreground'), grid = token('chart-grid'), axis = token('chart-axis')
  return {
    aria: { enabled: true },
    animation: false,
    textStyle: { fontFamily: 'Geist Variable, ui-sans-serif, system-ui', fontSize: 12, color: text },
    grid: { left: 8, right: 8, top: 16, bottom: 4, containLabel: true },
    axisCommon: { axisLine: { lineStyle: { color: axis } }, splitLine: { lineStyle: { color: grid } }, axisLabel: { color: text } },
    tooltip: {
      backgroundColor: token('popover'), borderColor: token('border'), borderWidth: 1, padding: [8, 10],
      textStyle: { color: token('foreground'), fontSize: 12 }, extraCssText: `box-shadow:${token('shadow-float')};border-radius:12px;`,
    },
  }
}
