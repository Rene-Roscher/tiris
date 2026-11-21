<script setup lang="ts">
/** Empty, error, missing-setup states: say what happened and offer one next step. */
import { CircleAlert, Inbox, PlugZap } from '@lucide/vue'
import { Button } from '@/components/ui/button'

withDefaults(defineProps<{ kind?: 'empty' | 'error' | 'setup'; title: string; body?: string; action?: string; busy?: boolean }>(),
  { kind: 'empty' })
defineEmits<{ action: [] }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center" :role="kind === 'error' ? 'alert' : undefined">
    <CircleAlert v-if="kind === 'error'" class="size-5 text-bad" aria-hidden="true" />
    <PlugZap v-else-if="kind === 'setup'" class="size-5 text-muted-foreground" aria-hidden="true" />
    <Inbox v-else class="size-5 text-muted-foreground" aria-hidden="true" />
    <p class="font-medium">{{ title }}</p>
    <p v-if="body" class="max-w-md text-sm text-muted-foreground">{{ body }}</p>
    <Button v-if="action" type="button" variant="outline" size="sm" class="mt-2" :disabled="busy" @click="$emit('action')">{{ action }}</Button>
  </div>
</template>
