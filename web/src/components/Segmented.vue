<script setup lang="ts" generic="T extends string | number">
/** Quiet segmented control. The chosen surface slides to the new option (a transition, so a quick second click
    starts from where it is); it appears without motion the first time. */
import { useResizeObserver } from '@vueuse/core'
import { nextTick, onMounted, ref, watch } from 'vue'

const props = defineProps<{ options: { value: T; label: string }[]; label: string }>()
const model = defineModel<T>({ required: true })
const root = ref<HTMLElement | null>(null)
const pill = ref<{ x: number; w: number } | null>(null)
const ready = ref(false)
function measure() {
  const i = props.options.findIndex((o) => o.value === model.value)
  const el = root.value?.children[i + 1] as HTMLElement | undefined   // child 0 is the pill
  pill.value = el ? { x: el.offsetLeft, w: el.offsetWidth } : null
}
onMounted(async () => { measure(); await nextTick(); requestAnimationFrame(() => { ready.value = true }) })
watch([model, () => props.options.map((o) => o.label).join('|')], () => nextTick(measure))
useResizeObserver(root, measure)
</script>

<template>
  <div ref="root" class="relative flex gap-0.5" role="group" :aria-label="label">
    <span v-if="pill" class="absolute inset-y-0 left-0 rounded-md bg-muted" aria-hidden="true"
          :class="ready ? 'transition-[translate,width] duration-(--ease-settle-ms) ease-settle' : ''"
          :style="{ translate: `${pill.x}px 0`, width: `${pill.w}px` }" />
    <button v-for="o in options" :key="String(o.value)" type="button" :aria-pressed="model === o.value"
            class="relative h-7 rounded-md px-2.5 text-sm font-medium transition-[color]"
            :class="model === o.value ? 'text-foreground' : 'text-caption hover:text-foreground'"
            @click="model = o.value">
      {{ o.label }}
    </button>
  </div>
</template>
