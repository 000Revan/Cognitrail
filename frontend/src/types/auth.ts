import type { UserPublic } from './user'

export interface LoginRequest { username: string; password: string }
export interface RegisterRequest extends LoginRequest { nickname?: string | null }
export interface LoginResponse {
  accessToken: string
  tokenType: 'bearer'
  expiresIn: number
  user: UserPublic
}
