import axios from 'axios'
import type { ApiResponse, ErrorData } from '../types/common'
import { getAccessToken, handleUnauthorized } from './session'

export class ApiError extends Error {
  constructor(message: string, public status: number, public errorCode: string, public requestId?: string, public details?: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 10000,
})

http.interceptors.request.use(config => {
  const token = getAccessToken()
  if (token && !config.url?.match(/\/auth\/(login|register)$/)) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
})

http.interceptors.response.use(
  response => response,
  error => {
    if (axios.isAxiosError<ApiResponse<ErrorData>>(error)) {
      if (error.response?.status === 401) handleUnauthorized(error.config?.headers.get('Authorization'))
      const payload = error.response?.data
      const validPayload = payload && typeof payload === 'object' && typeof payload.msg === 'string'
      return Promise.reject(new ApiError(
        validPayload ? payload.msg : '无法连接服务，请确认后端已启动',
        error.response?.status || 0,
        validPayload ? payload.data?.errorCode || 'REQUEST_FAILED' : 'NETWORK_ERROR',
        validPayload ? payload.data?.requestId : undefined,
        validPayload ? payload.data?.details : undefined,
      ))
    }
    return Promise.reject(error)
  },
)
