<script setup lang="ts">
/*
  Toast pill, from the ui-motion toast example (Rene-Roscher/skills). vue-sonner places, stacks and
  pauses; shape, timing and the drag come from here. Changes against the demo (interface-motion):
  - a press on a pill that is still springing back catches it where it is on screen, and the pointer continues
    the rubber band from there (the demo restarted at 0 and jumped);
  - at a catch the waiting pills keep the peek value that matches how far the pill has come back.
*/
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { useI18n } from 'vue-i18n'
import type { PillState } from '@/lib/toast'

const props = defineProps<{ state: PillState; isPaused?: boolean }>()
const { t } = useI18n()
const s = props.state

const RING = 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18'
const MARKS: Record<string, string[]> = {
  success: ['M8.25 12.4l2.65 2.65 4.85-5.4'],
  error: ['M9.6 9.6l4.8 4.8', 'M14.4 9.6l-4.8 4.8'],
  warning: ['M12 7.8v4.9', 'M12 16.2h.01'],
  info: ['M12 11.3v4.9', 'M12 7.8h.01'],
  loading: [],
}

const root = ref<HTMLElement | null>(null)
const inner = ref<HTMLElement | null>(null)
const open = ref(false)
const w = ref(44)
const hgt = ref(44)
const w0 = ref(44)
const ownW = ref(44)
const timerKey = ref(0)
const lineMs = ref(0)
const front = ref(true)
const paused = computed(() => props.isPaused || !front.value)
let li: HTMLElement | null = null
let ol: HTMLElement | null = null
let ro: ResizeObserver | undefined
let mo: MutationObserver | undefined
let openTimer: ReturnType<typeof setTimeout> | undefined
let timer: ReturnType<typeof setTimeout> | null = null
let startedAt = 0
let remaining = 0

const life = computed(() => (s.type === 'loading' ? 0 : (s.duration ?? (s.action ? 8000 : s.type === 'error' ? 6000 : 4000))))
const countdown = computed(() => life.value > 0 && Boolean(s.action))
const closable = computed(() => s.type === 'error' && !s.action)
const textKey = computed(() => `${s.title}|${s.description ?? ''}`)
const dismiss = () => toast.dismiss(s.id)

function run() {
  if (paused.value || timer !== null || remaining <= 0) return
  startedAt = performance.now()
  timer = setTimeout(dismiss, remaining)
}
function hold() {
  if (timer === null) return
  clearTimeout(timer)
  timer = null
  remaining = Math.max(0, remaining - (performance.now() - startedAt))
}
function arm() {
  if (timer !== null) clearTimeout(timer)
  timer = null
  remaining = life.value
  lineMs.value = life.value
  timerKey.value++
  run()
}
watch(front, (isFront, wasFront) => {
  if (isFront && !wasFront && remaining > 0 && remaining < 2500) {
    remaining = 2500
    lineMs.value = 2500
    timerKey.value++
  }
})
watch(paused, (p) => (p ? hold() : run()))
watch(() => s.lifeRev, arm)
watch(
  () => s.count,
  () => root.value?.animate([{ scale: '1' }, { scale: '1.04' }, { scale: '1' }], { duration: 360, easing: 'cubic-bezier(.3,.7,.4,1)' }),
)

function publish() {
  if (!ol || !inner.value) return
  if (front.value) ol.style.setProperty('--lp-front-w', `${inner.value.offsetWidth}px`)
  if (li?.getAttribute('data-index') === '1') {
    ol.style.setProperty('--lp-next-w', `${inner.value.offsetWidth}px`)
    ol.style.setProperty('--lp-next-h', `${inner.value.offsetHeight}px`)
  }
}
function fit() {
  const el = inner.value
  if (!el) return
  hgt.value = el.offsetHeight
  ownW.value = el.offsetWidth
  if (open.value) w.value = el.offsetWidth
  publish()
}
function syncPeek() {
  if (li && ol && front.value && li.getAttribute('data-removed') === 'true') ol.style.setProperty('--lp-peek', '1')
}

/* Drag: free in any direction with a rubber band (1:1 for 16 px, then towards 72 px). */
const PEEK_DISTANCE = 60
const FLING_DISTANCE = 80
const FLING_SPEED = 0.45 // px per ms over the last 100 ms
const FREE = 16
const REACH = 72
const SOFT = 60
const BLEND = 24 // px of pointer travel over which a caught peek value blends back into the usual mapping
const rubber = (d: number) => (d <= FREE ? d : FREE + (REACH - FREE) * (1 - Math.exp(-(d - FREE) / SOFT)))
const unrubber = (v: number) => (v <= FREE ? v : FREE - SOFT * Math.log(1 - (Math.min(v, REACH - 0.01) - FREE) / (REACH - FREE)))
const dx = ref(0)
const dy = ref(0)
const dragging = ref(false)
const flung = ref(false)
type Sample = { t: number; x: number; y: number }
let drag: { id: number; x0: number; y0: number; samples: Sample[]; raw?: number; rx?: number; ry?: number; caught?: boolean; peekDiff?: number; px?: number; py?: number } | null = null
// set while the pill springs back: what a catch needs to restore the shared peek value
let returning: { x: number; y: number; peek: number; until: number } | null = null
let peekNow = 0
const peek = (p: number) => {
  peekNow = p
  ol?.style.setProperty('--lp-peek', String(+p.toFixed(3)))
}

function onDown(e: PointerEvent) {
  const el = root.value
  if (!el || !li || e.button !== 0 || (e.target as HTMLElement).closest('button') || !front.value || flung.value) return
  let ox = 0
  let oy = 0
  let caught = false
  let peekDiff = 0
  if (returning && performance.now() < returning.until) {
    // Catch: read the offset on screen, freeze it (is-dragging leaves translate out of the transition)
    const tr = getComputedStyle(el).translate
    ;[ox = 0, oy = 0] = !tr || tr === 'none' ? [] : tr.split(' ').map(parseFloat)
    const rel2 = returning.x ** 2 + returning.y ** 2
    const progress = rel2 > 0 ? (ox * returning.x + oy * returning.y) / rel2 : 0
    let shownPeek = returning.peek * progress
    // The waiting pill can trail by a frame (WebKit): take the peek its width on screen says, when it spans enough.
    const next = ol?.querySelector<HTMLElement>('[data-sonner-toast][data-index="1"] .lp')
    if (next && ol) {
      const from = parseFloat(ol.style.getPropertyValue('--lp-front-w'))
      const to = parseFloat(next.style.getPropertyValue('--lp-own-w'))
      if (Math.abs(to - from) > 8) shownPeek = Math.max(-0.5, Math.min(1, (parseFloat(getComputedStyle(next).width) - from) / (to - from))) // below 0 while it overshoots
    }
    const shown = Math.hypot(ox, oy)
    peekDiff = shownPeek - Math.min(1, unrubber(shown) / PEEK_DISTANCE)
    caught = true
    dx.value = ox
    dy.value = oy
    dragging.value = true
    ol?.setAttribute('data-lp-dragging', '')
    peek(shownPeek)
  }
  returning = null
  // pointer origin so that the first move continues the curve: press minus the offset in pointer space
  const shown = Math.hypot(ox, oy)
  const back = shown > 0.01 ? unrubber(shown) / shown : 1
  drag = {
    id: e.pointerId,
    x0: e.clientX - ox * back,
    y0: e.clientY - oy * back,
    px: e.clientX,
    py: e.clientY,
    caught,
    peekDiff,
    samples: [{ t: e.timeStamp, x: e.clientX, y: e.clientY }],
  }
  el.setPointerCapture(e.pointerId)
}
function onMove(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return
  const x = e.clientX - drag.x0
  const y = e.clientY - drag.y0
  if (!dragging.value && Math.hypot(x, y) < 3) return // still a click
  if (!dragging.value) ol?.setAttribute('data-lp-dragging', '')
  dragging.value = true
  const raw = Math.hypot(x, y)
  const k = raw > 0 ? rubber(raw) / raw : 1
  dx.value = x * k
  dy.value = y * k
  drag.raw = raw
  drag.rx = x
  drag.ry = y
  drag.samples.push({ t: e.timeStamp, x: e.clientX, y: e.clientY })
  if (drag.samples.length > 8) drag.samples.shift()
  const travel = Math.hypot(e.clientX - (drag.px ?? e.clientX), e.clientY - (drag.py ?? e.clientY))
  const diff = drag.caught ? (drag.peekDiff ?? 0) * Math.exp(-travel / BLEND) : 0
  peek(Math.max(-0.5, Math.min(1, raw / PEEK_DISTANCE + diff)))
}
function onUp(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return
  const { samples, raw = 0, rx = 0, ry = 0, caught } = drag
  drag = null
  ol?.removeAttribute('data-lp-dragging')
  if (!dragging.value) return
  dragging.value = false
  const last = samples.at(-1)!
  const first = samples.find((p) => last.t - p.t <= 100) ?? samples[0]!
  const dt = Math.max(1, last.t - first.t)
  const vx = (last.x - first.x) / dt
  const vy = (last.y - first.y) / dt
  const speed = e.timeStamp - last.t > 80 || samples.length < 2 ? 0 : Math.hypot(vx, vy)
  if (raw > FLING_DISTANCE || (speed > FLING_SPEED && raw > 12)) {
    const ux = speed > 0.2 ? vx / speed : rx / raw
    const uy = speed > 0.2 ? vy / speed : ry / raw
    const reach = Math.min(220, Math.max(140, speed * 260))
    flung.value = true
    dx.value += ux * reach
    dy.value += uy * reach
    peek(1)
    setTimeout(dismiss, 260)
  } else {
    if (caught || dx.value || dy.value) {
      const ms = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--lp-enter-ms')) || 540
      returning = { x: dx.value, y: dy.value, peek: peekNow, until: performance.now() + ms }
    }
    dx.value = 0
    dy.value = 0
    peek(0)
  }
}
function onCancel() {
  if (!drag) return
  drag = null
  dragging.value = false
  ol?.removeAttribute('data-lp-dragging')
  dx.value = 0
  dy.value = 0
  peek(0)
}

onMounted(() => {
  const el = root.value!
  li = el.closest('[data-sonner-toast]')
  ol = li?.parentElement ?? null
  const H = inner.value!.offsetHeight
  hgt.value = H
  w.value = H
  w0.value = H
  // Sonner measures the height right after this hook: give it the final value, without a transition.
  el.style.transition = 'none'
  el.style.height = `${H}px`
  el.style.width = `${H}px`
  void el.offsetWidth
  el.style.transition = ''
  ownW.value = inner.value!.offsetWidth
  front.value = li ? li.getAttribute('data-front') === 'true' : true
  if (front.value) ol?.style.setProperty('--lp-peek', '0')
  publish()
  ro = new ResizeObserver(fit)
  ro.observe(inner.value!)
  if (li) {
    mo = new MutationObserver(() => {
      const was = front.value
      front.value = li!.getAttribute('data-front') === 'true'
      if (was && !front.value) ol?.style.setProperty('--lp-peek', '0')
      publish()
      syncPeek()
    })
    mo.observe(li, { attributes: true, attributeFilter: ['data-front', 'data-index', 'data-removed'] })
  }
  // the shape lands first, then the pill opens
  openTimer = setTimeout(() => {
    open.value = true
    fit()
  }, 200)
  arm()
})

onBeforeUnmount(() => {
  clearTimeout(openTimer)
  if (timer !== null) clearTimeout(timer)
  ro?.disconnect()
  mo?.disconnect()
  if (front.value) ol?.style.setProperty('--lp-peek', '0')
  s.end?.()
})

function act() {
  s.action?.onClick()
  dismiss()
}
// leaving text keeps its width, or it would wrap again while it fades
function freeze(el: Element) {
  ;(el as HTMLElement).style.width = `${(el as HTMLElement).offsetWidth}px`
}
</script>

<template>
  <div
    ref="root"
    class="lp"
    :class="{ 'is-open': open, 'is-dragging': dragging, 'is-flung': flung }"
    :data-type="s.type"
    :role="s.type === 'error' ? 'alert' : 'status'"
    :style="{ width: w + 'px', height: hgt + 'px', translate: dx + 'px ' + dy + 'px', '--lp-w0': w0 + 'px', '--lp-own-w': ownW + 'px', '--lp-own-h': hgt + 'px' }"
    @pointerdown="onDown"
    @pointermove="onMove"
    @pointerup="onUp"
    @pointercancel="onCancel"
  >
    <div ref="inner" class="lp-inner">
      <span class="lp-icon">
        <Transition name="lp-swap">
          <span :key="s.type" class="lp-glyph" :data-type="s.type">
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
              <path class="lp-ring" :d="RING" pathLength="1" />
              <path v-for="d in MARKS[s.type] ?? []" :key="d" :d="d" pathLength="1" />
            </svg>
          </span>
        </Transition>
      </span>
      <span class="lp-copy">
        <Transition name="lp-text" @before-leave="freeze">
          <span :key="textKey" class="lp-text">
            <span class="lp-title">{{ s.title }}<span v-if="s.count > 1" :key="'c' + s.count" class="lp-count">{{ s.count }}×</span></span>
            <span v-if="s.description" class="lp-desc">{{ s.description }}</span>
          </span>
        </Transition>
      </span>
      <Transition name="lp-act">
        <span v-if="s.action || closable" :key="(s.action?.label ?? '') + '|' + closable" class="lp-actions">
          <button v-if="s.action" type="button" class="lp-btn" @click="act">{{ s.action.label }}</button>
          <button v-if="closable" type="button" class="lp-close" :aria-label="t('common.close')" @click="dismiss">
            <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
          </button>
        </span>
      </Transition>
    </div>
    <span v-if="s.progress != null" class="lp-progress"><i :style="{ transform: 'scaleX(' + s.progress + ')' }"></i></span>
    <span
      v-if="countdown"
      :key="timerKey"
      class="lp-timer"
      :style="{ animationDuration: lineMs + 'ms', animationPlayState: paused ? 'paused' : 'running' }"
    ></span>
  </div>
</template>
