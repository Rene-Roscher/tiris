<script setup lang="ts">
import { Menu, Search } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'
import { Toaster } from 'vue-sonner'
import AppSidebar from '@/components/AppSidebar.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import ConfirmHost from '@/components/ConfirmHost.vue'
import LoginScreen from '@/components/LoginScreen.vue'
import Logo from '@/components/Logo.vue'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useTheme } from '@/composables/useTheme'
import { paletteOpen } from '@/lib/palette'

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
    <div class="md:grid md:min-h-dvh md:grid-cols-[228px_minmax(0,1fr)]">
      <aside class="sticky top-0 hidden h-dvh md:block">
        <AppSidebar />
      </aside>
      <div class="min-w-0 md:py-2 md:pr-2">
        <div class="flex min-h-dvh flex-col bg-background md:min-h-[calc(100dvh-16px)] md:rounded-xl md:border md:border-border md:shadow-xs">
          <header class="sticky top-0 z-raised flex h-12 items-center gap-2 border-b border-border bg-background px-4 md:hidden">
            <Button type="button" variant="ghost" size="icon-sm" :aria-label="t('app.openMenu')" @click="mobileOpen = true">
              <Menu class="size-4" aria-hidden="true" />
            </Button>
            <Logo />
            <span class="font-semibold">tiris</span>
            <span class="flex-1" aria-hidden="true" />
            <Button type="button" variant="ghost" size="icon-sm" :aria-label="t('palette.title')" @click="paletteOpen = true">
              <Search class="size-4" aria-hidden="true" />
            </Button>
          </header>
          <main class="w-full max-w-[1120px] flex-1 self-center px-4 pb-16 pt-4 md:px-10 md:pt-5">
            <RouterView />
          </main>
        </div>
      </div>
    </div>
    <Sheet v-model:open="mobileOpen">
      <SheetContent side="left" class="w-64 bg-canvas p-0">
        <SheetTitle class="sr-only">tiris</SheetTitle>
        <SheetDescription class="sr-only">{{ t('app.tagline') }}</SheetDescription>
        <AppSidebar @navigate="mobileOpen = false" />
      </SheetContent>
    </Sheet>
    <CommandPalette v-model:open="paletteOpen" />
    <ConfirmHost />
    <Toaster
      class="lp-toaster z-toast"
      position="bottom-center"
      :offset="{ bottom: 32 }"
      :mobile-offset="{ bottom: 16 }"
      :expand="false"
      :visible-toasts="3"
      :gap="8"
      :container-aria-label="t('app.notifications')"
    />
  </TooltipProvider>
</template>
