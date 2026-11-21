import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createApp } from 'vue'
import App from './App.vue'
import { i18n } from './i18n'
import { installSprings } from './lib/motion'
import { router } from './router'
import './styles/app.css'

installSprings()

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: true, retry: 1 } },
})

createApp(App).use(router).use(i18n).use(VueQueryPlugin, { queryClient }).mount('#app')
