<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Logo from '@/components/Logo.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api } from '@/lib/api'

const emit = defineEmits<{ done: [] }>()
const { t } = useI18n()
const password = ref('')
const error = ref('')
const busy = ref(false)
async function submit() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await api.post('/api/auth/login', { password: password.value })
    emit('done')
  } catch {
    error.value = t('settings.wrongPassword')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="flex min-h-dvh items-center justify-center px-4">
    <form class="flex w-full max-w-xs flex-col gap-4" @submit.prevent="submit">
      <div class="flex items-center gap-2"><Logo /><span class="text-md font-semibold">tiris</span></div>
      <div class="grid gap-1.5">
        <Label for="pw">{{ t('settings.password') }}</Label>
        <Input id="pw" v-model="password" type="password" autocomplete="current-password" required autofocus :aria-invalid="!!error" />
        <p v-if="error" class="text-sm text-bad" role="alert">{{ error }}</p>
      </div>
      <Button type="submit" :disabled="busy">{{ t('settings.login') }}</Button>
    </form>
  </div>
</template>
