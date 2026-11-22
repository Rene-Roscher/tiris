<script setup lang="ts">
import type { DialogOverlayProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { cn } from '@/lib/utils'
import { DialogOverlay } from "reka-ui"

const props = defineProps<DialogOverlayProps & { class?: HTMLAttributes["class"] }>()

const delegatedProps = reactiveOmit(props, "class")
</script>

<template>
  <DialogOverlay
    data-slot="dialog-overlay"
    v-bind="delegatedProps"
    :class="cn('fixed inset-0 z-modal bg-black/40 backdrop-blur-[2px] dark:bg-black/60', props.class)"
  >
    <slot />
  </DialogOverlay>
</template>
