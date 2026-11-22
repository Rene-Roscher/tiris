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

/** Charts appear without animation; when their data changes (range, legend), they move to the new state in 280 ms.
    Live charts do not use this: a sliding window that eases every 2 s would never be still. */
export function animated() {
  const reduce = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
  return reduce ? { animation: false } : { animation: true, animationDuration: 0, animationDurationUpdate: 280, animationEasingUpdate: 'cubicOut' as const }
}

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

/** Mix two #rrggbb colours (t = 0 gives a, 1 gives b); one-hue scales from a surface to the accent. */
export function mix(a: string, b: string, t: number) {
  const p = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
  const [x, y] = [p(a), p(b)]
  return `#${x.map((v, i) => Math.round(v + (y[i]! - v) * t).toString(16).padStart(2, '0')).join('')}`
}
