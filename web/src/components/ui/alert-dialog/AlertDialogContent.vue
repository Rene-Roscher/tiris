<script setup lang="ts">
import type { AlertDialogContentEmits, AlertDialogContentProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { cn } from '@/lib/utils'
import {
  AlertDialogContent,
  AlertDialogOverlay,
  AlertDialogPortal,
  useForwardPropsEmits,
} from "reka-ui"

defineOptions({
  inheritAttrs: false,
})

const props = defineProps<AlertDialogContentProps & { class?: HTMLAttributes["class"] }>()
const emits = defineEmits<AlertDialogContentEmits>()

const delegatedProps = reactiveOmit(props, "class")

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <AlertDialogPortal>
    <Transition name="t-fade">
    <AlertDialogOverlay
      data-slot="alert-dialog-overlay"
      class="fixed inset-0 z-confirm bg-black/40 backdrop-blur-[2px] dark:bg-black/60"
    />
    </Transition>
    <Transition name="t-dialog">
    <AlertDialogContent
      data-slot="alert-dialog-content"
      v-bind="{ ...$attrs, ...forwarded }"
      :class="
        cn(
          'bg-background fixed top-[50%] left-[50%] z-confirm grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-xl border bg-popover p-5 shadow-float sm:max-w-md',
          props.class,
        )
      "
    >
      <slot />
    </AlertDialogContent>
    </Transition>
  </AlertDialogPortal>
</template>
