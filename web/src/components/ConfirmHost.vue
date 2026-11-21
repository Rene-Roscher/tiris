<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { pending } from '@/composables/useConfirm'
import { buttonVariants } from '@/components/ui/button'

const { t } = useI18n()
const open = computed({
  get: () => pending.value !== null,
  set: (v) => { if (!v) settle(false) },
})
function settle(ok: boolean) {
  const p = pending.value
  pending.value = null
  p?.resolve(ok)
}
</script>

<template>
  <AlertDialog v-model:open="open">
    <AlertDialogContent v-if="pending">
      <AlertDialogHeader>
        <AlertDialogTitle>{{ pending.title }}</AlertDialogTitle>
        <AlertDialogDescription v-if="pending.body">{{ pending.body }}</AlertDialogDescription>
      </AlertDialogHeader>
      <pre v-if="pending.detail" class="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-muted px-3 py-2 font-sans text-sm text-muted-foreground">{{ pending.detail }}</pre>
      <AlertDialogFooter>
        <AlertDialogCancel type="button" @click="settle(false)">{{ t('common.cancel') }}</AlertDialogCancel>
        <AlertDialogAction type="button" :class="pending.danger ? buttonVariants({ variant: 'destructive' }) : ''" @click="settle(true)">
          {{ pending.action }}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
