import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      redirect: '/monitor',
    },
    {
      path: '/monitor',
      name: 'monitor',
      component: () => import('@/views/MonitorView.vue'),
    },
    {
      path: '/drones',
      name: 'drones',
      component: () => import('@/views/DronesView.vue'),
    },
  ],
})

// 全局守卫：未登录一律回登录页；已登录访问 /login 回监控页
router.beforeEach((to) => {
  const auth = useAuthStore()
  auth.restore()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'monitor' }
  }
  return true
})

export default router
