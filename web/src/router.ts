import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('@/views/OverviewView.vue') },
    { path: '/live', component: () => import('@/views/LiveView.vue') },
    { path: '/devices', component: () => import('@/views/DevicesView.vue') },
    { path: '/devices/:id', component: () => import('@/views/DeviceDetailView.vue') },
    { path: '/costs', component: () => import('@/views/CostsView.vue') },
    { path: '/settings', component: () => import('@/views/SettingsView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
