import type { EntityId } from './common'

export type AccountStatus = 'active' | 'disabled'
export interface UserPublic {
  id: EntityId
  username: string
  nickname: string
  avatarUrl?: string | null
  bio?: string
  role: 'user' | 'admin'
  status: AccountStatus
  createdAt: string
}
export interface ProfileUpdate { nickname: string; bio: string }
export interface PrivacySettings {
  publishPublic: boolean
  topicPublic: boolean
  checkinPublic: boolean
  favoritePublic: boolean
  learningPublic: boolean
  settingsVersion: number
}
