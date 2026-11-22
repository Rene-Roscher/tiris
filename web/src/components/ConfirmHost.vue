<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { pending } from '@/composables/useConfirm'

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
        <!-- plain buttons: Reka's Action/Cancel close the dialog first, and that close used to answer "no" before the click said "yes" -->
        <Button type="button" variant="outline" @click="settle(false)">{{ t('common.cancel') }}</Button>
        <Button type="button" :variant="pending.danger ? 'destructive' : 'default'" @click="settle(true)">{{ pending.action }}</Button>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
