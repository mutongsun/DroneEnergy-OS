import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi } from '@/api/auth'
import type { UserRole } from '@/types/api'

const TOKEN_KEY = 'token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const username = ref<string>('')
  const role = ref<UserRole | null>(null)

  const isAuthenticated = computed(() => token.value !== null)
  const canWrite = computed(() => role.value === 'operator' || role.value === 'admin')

  async function login(user: string, password: string): Promise<void> {
    const resp = await loginApi(user, password)
    token.value = resp.access_token
    username.value = resp.username
    role.value = resp.role
    localStorage.setItem(TOKEN_KEY, resp.access_token)
    // 用户名与角色仅用于界面展示（写按钮可见性），随 token 一起持久化，
    // 刷新页面不丢失；真正的权限校验始终在后端
    localStorage.setItem('username', resp.username)
    localStorage.setItem('role', resp.role)
  }

  function logout(): void {
    token.value = null
    username.value = ''
    role.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem('username')
    localStorage.removeItem('role')
  }

  // 刷新页面时从 localStorage 恢复展示信息（token 已在 ref 初始化时恢复）
  function restore(): void {
    username.value = localStorage.getItem('username') ?? ''
    const savedRole = localStorage.getItem('role')
    role.value = (savedRole as UserRole | null) ?? null
  }

  return { token, username, role, isAuthenticated, canWrite, login, logout, restore }
})
