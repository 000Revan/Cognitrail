import type { ApiResponse } from '../types/common'
import type { LoginRequest, LoginResponse, RegisterRequest } from '../types/auth'
import type { UserPublic } from '../types/user'
import { http } from './http'

export async function login(data: LoginRequest) {
  return (await http.post<ApiResponse<LoginResponse>>('/api/v1/auth/login', data)).data.data
}
export async function register(data: RegisterRequest) {
  return (await http.post<ApiResponse<UserPublic>>('/api/v1/auth/register', data)).data.data
}
export async function logout() {
  await http.post<ApiResponse<null>>('/api/v1/auth/logout')
}
