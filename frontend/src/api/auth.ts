import { http } from './http'
import type { TokenResponse } from '@/types/api'

export async function login(username: string, password: string): Promise<TokenResponse> {
  const { data } = await http.post<TokenResponse>('/auth/login', { username, password })
  return data
}
