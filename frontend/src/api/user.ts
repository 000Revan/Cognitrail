import type { ApiResponse, Page } from '../types/common'
import type { AccountStatus, PrivacySettings, ProfileUpdate, UserPublic } from '../types/user'
import { http } from './http'
import type { PublicRoadmap } from '../types/roadmap'

export interface PublicIdentity { id: string; username: string; nickname: string; avatarUrl: string | null; bio: string | null }
export interface FollowPerson extends PublicIdentity { isFollowing: boolean; canFollow: boolean }
export async function getRelationships(id: string, kind: 'following' | 'followers', page = 1) {
  return (await http.get<ApiResponse<Page<FollowPerson>>>('/api/v1/users/' + encodeURIComponent(id) + '/' + kind, { params: { page } })).data.data
}
export interface FollowState { isFollowing: boolean; followerCount: number; followingCount: number }
export interface PublicProfile extends PublicIdentity, FollowState { canFollow: boolean; canViewFavorites: boolean; canViewLearning: boolean; favoriteCount: number | null; learningCount: number | null; roadmaps: Page<PublicRoadmap> }
export interface ActivitySummary { id: string; actorId: string; nickname: string; avatarUrl: string | null; activityType: 'publish' | 'topic' | 'checkin'; occurredOn: string; createdAt: string; routeCount: number; roadmapId: string | null; title: string | null; issueId?: string | null }
export interface MyDiscussion { id: string; issueId: string; roadmapId: string; roadmapTitle: string; title: string; body: string; status: string; commentId: string | null; createdAt: string }
export async function getPublicProfile(id: string, page = 1, pageSize = 12) {
  return (await http.get<ApiResponse<PublicProfile>>('/api/v1/users/' + encodeURIComponent(id) + '/profile', { params: { page, pageSize } })).data.data
}
export async function changeFollow(id: string, enabled: boolean) {
  const path = '/api/v1/users/' + encodeURIComponent(id) + '/follow'
  return (enabled ? await http.put<ApiResponse<FollowState>>(path) : await http.delete<ApiResponse<FollowState>>(path)).data.data
}
export async function getActivities(id: string | null, page = 1, pageSize = 12) {
  return (await http.get<ApiResponse<Page<ActivitySummary>>>(id ? '/api/v1/users/' + encodeURIComponent(id) + '/activities' : '/api/v1/users/me/feed', { params: { page, pageSize } })).data.data
}
export async function getPublicCollection(id: string, category: 'favorite' | 'learning', page = 1, pageSize = 12) {
  return (await http.get<ApiResponse<Page<PublicRoadmap>>>('/api/v1/users/' + encodeURIComponent(id) + '/collections', { params: { category, page, pageSize } })).data.data
}
export async function getFollowing(page = 1) {
  return (await http.get<ApiResponse<Page<PublicIdentity>>>('/api/v1/users/me/following', { params: { page } })).data.data
}
export async function roadmapSubscription(id: string, subscribed?: boolean) {
  const path = '/api/v1/roadmaps/' + encodeURIComponent(id) + '/subscription'
  return (subscribed === undefined ? await http.get<ApiResponse<{ subscribed: boolean }>>(path) : await http.put<ApiResponse<{ subscribed: boolean }>>(path, { subscribed })).data.data
}
export async function getMyDiscussions(kind: 'questions' | 'replies', page = 1) {
  return (await http.get<ApiResponse<Page<MyDiscussion>>>('/api/v1/users/me/discussions', { params: { kind, page } })).data.data
}

export async function getMe() {
  return (await http.get<ApiResponse<UserPublic>>('/api/v1/users/me')).data.data
}
export async function uploadAvatar(file: File) {
  return (await http.post<ApiResponse<UserPublic>>('/api/v1/users/me/avatar', file, {
    headers: { 'Content-Type': file.type || 'application/octet-stream' },
  })).data.data
}
export async function updateMe(data: ProfileUpdate) {
  return (await http.patch<ApiResponse<UserPublic>>('/api/v1/users/me', data)).data.data
}
export async function changePassword(oldPassword: string, newPassword: string) {
  await http.patch<ApiResponse<null>>('/api/v1/users/me/password', { oldPassword, newPassword })
}
export async function getPrivacy() {
  return (await http.get<ApiResponse<PrivacySettings>>('/api/v1/users/me/privacy')).data.data
}
export async function updatePrivacy(data: PrivacySettings) {
  return (await http.patch<ApiResponse<PrivacySettings>>('/api/v1/users/me/privacy', data)).data.data
}
export async function adminAccounts(params: { keyword?: string; role?: string; status?: string; page?: number }) {
  return (await http.get<ApiResponse<Page<UserPublic>>>('/api/v1/admin/users', { params })).data.data
}
export async function setAccountStatus(user: UserPublic, status: AccountStatus) {
  return (await http.patch<ApiResponse<UserPublic>>('/api/v1/admin/users/' + user.id + '/status', {
    status, expectedStatus: user.status,
  })).data.data
}
export async function createAccount(data: { username: string; nickname: string | null; password: string; role: 'user' | 'admin' }) {
  return (await http.post<ApiResponse<UserPublic>>('/api/v1/admin/users', data)).data.data
}
export async function editAccount(user: UserPublic, nickname: string) {
  return (await http.patch<ApiResponse<UserPublic>>('/api/v1/admin/users/' + user.id, {
    nickname, expectedNickname: user.nickname,
  })).data.data
}
export async function resetAccountPassword(id: string, newPassword: string) {
  await http.post<ApiResponse<null>>('/api/v1/admin/users/' + id + '/reset-password', { newPassword })
}
