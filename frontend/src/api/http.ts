import axios from 'axios'

/**
 * 统一 HTTP 客户端：
 * - 请求拦截：自动附带 JWT
 * - 响应拦截：401 时清除本地凭据并跳登录页（token 过期统一收口）
 */
export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 10_000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401 && !location.pathname.startsWith('/login')) {
      localStorage.removeItem('token')
      location.assign('/login')
    }
    return Promise.reject(error)
  },
)
