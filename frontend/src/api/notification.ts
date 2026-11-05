import { http } from './http'
import type { ApiResponse, Page } from '../types/common'

export interface Notification { id: string; type: string; readAt: string | null; createdAt: string }
export interface NotificationPage extends Page<Notification> { latestId?: string | null }
export async function notifications(page: number, unread: boolean) {
  return (await http.get<ApiResponse<NotificationPage>>('/api/v1/notifications', { params: { page, unread } })).data.data
}
export async function deleteNotification(id: string) {
  return (await http.delete<ApiResponse<{ deletedCount: number }>>('/api/v1/notifications/' + encodeURIComponent(id))).data.data
}
export async function deleteNotificationHistory(throughId: string, readOnly = false) {
  return (await http.delete<ApiResponse<{ deletedCount: number }>>('/api/v1/notifications', { data: { throughId, readOnly } })).data.data
}
export async function unreadCount() {
  return (await http.get<ApiResponse<{ count: number }>>('/api/v1/notifications/unread-count')).data.data.count
}
export async function readNotification(id: string) {
  await http.patch('/api/v1/notifications/' + encodeURIComponent(id) + '/read')
}
export async function readThrough(throughId: string) {
  await http.patch('/api/v1/notifications/read', { throughId })
}
export async function notificationTarget(id: string) {
  return (await http.get<ApiResponse<{ accessible: boolean; path: string | null; message: string | null }>>('/api/v1/notifications/' + encodeURIComponent(id) + '/target')).data.data
}
export function notificationLabel(type: string) {
  return ({ issue_created: '你的路线收到了新话题', comment_created: '话题有了新回复', issue_state_changed: '话题处理状态有更新', release_published: '订阅的路线发布了新版' })[type] || '站内消息'
}
