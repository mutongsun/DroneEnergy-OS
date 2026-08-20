import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './auth'

const loginApi = vi.fn()

vi.mock('@/api/auth', () => ({
  login: (...args: unknown[]) => loginApi(...args),
}))

/** 内存版 localStorage：当前 vitest+jsdom 组合下原生实现不可用，stub 之 */
function stubLocalStorage(): void {
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  })
}

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    stubLocalStorage()
    loginApi.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('登录成功后写入 token 并具备写权限（operator）', async () => {
    loginApi.mockResolvedValue({
      access_token: 'jwt-xyz',
      token_type: 'bearer',
      username: 'op',
      role: 'operator',
    })
    const auth = useAuthStore()
    await auth.login('op', 'op123')

    expect(auth.isAuthenticated).toBe(true)
    expect(auth.token).toBe('jwt-xyz')
    expect(auth.username).toBe('op')
    expect(auth.role).toBe('operator')
    expect(auth.canWrite).toBe(true)
    expect(localStorage.getItem('token')).toBe('jwt-xyz')
  })

  it('viewer 只读：canWrite 为 false', async () => {
    loginApi.mockResolvedValue({
      access_token: 'jwt-readonly',
      token_type: 'bearer',
      username: 'view',
      role: 'viewer',
    })
    const auth = useAuthStore()
    await auth.login('view', 'view123')
    expect(auth.canWrite).toBe(false)
  })

  it('登出清除全部凭据', async () => {
    loginApi.mockResolvedValue({
      access_token: 'jwt-xyz',
      token_type: 'bearer',
      username: 'op',
      role: 'operator',
    })
    const auth = useAuthStore()
    await auth.login('op', 'op123')
    auth.logout()

    expect(auth.isAuthenticated).toBe(false)
    expect(auth.token).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
  })
})
