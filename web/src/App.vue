<script setup lang="ts">
import { Menu } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'
import { Toaster } from 'vue-sonner'
import AppSidebar from '@/components/AppSidebar.vue'
import ConfirmHost from '@/components/ConfirmHost.vue'
import LoginScreen from '@/components/LoginScreen.vue'
import Logo from '@/components/Logo.vue'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useTheme } from '@/composables/useTheme'

const { t } = useI18n()
useTheme()
const mobileOpen = ref(false)
// Login only when the server asks for it (TIRIS_PASSWORD set); API calls answering 401 raise 'tiris:login'.
const needLogin = ref(false)
onMounted(async () => {
  window.addEventListener('tiris:login', () => { needLogin.value = true })
  try {
    const r = await fetch('/api/auth/status').then((x) => x.json())
    needLogin.value = r.required && !r.authenticated
  } catch { /* server down: the views show their error states */ }
})
const loggedIn = () => window.location.reload()
</script>

<template>
  <LoginScreen v-if="needLogin" @done="loggedIn" />
  <TooltipProvider v-else :delay-duration="400" :skip-delay-duration="200">
    <div class="flex min-h-dvh">
      <aside class="sticky top-0 hidden h-dvh w-56 shrink-0 border-r border-border md:block">
        <AppSidebar />
      </aside>
      <div class="flex min-w-0 flex-1 flex-col">
        <header class="sticky top-0 z-raised flex h-12 items-center gap-2 border-b border-border bg-background px-4 md:hidden">
          <Button type="button" variant="ghost" size="icon-sm" :aria-label="t('app.openMenu')" @click="mobileOpen = true">
            <Menu class="size-4" aria-hidden="true" />
          </Button>
          <Logo />
          <span class="font-semibold">tiris</span>
        </header>
        <main class="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 md:px-8 md:py-8">
          <RouterView />
        </main>
      </div>
    </div>
    <Sheet v-model:open="mobileOpen">
      <SheetContent side="left" class="w-64 p-0">
        <SheetTitle class="sr-only">tiris</SheetTitle>
        <SheetDescription class="sr-only">{{ t('app.tagline') }}</SheetDescription>
        <AppSidebar @navigate="mobileOpen = false" />
      </SheetContent>
    </Sheet>
    <ConfirmHost />
    <Toaster position="bottom-center" :toast-options="{ unstyled: true }" class="z-toast" />
  </TooltipProvider>
</template>
