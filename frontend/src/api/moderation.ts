import { http } from './http'
import type { ApiResponse, Page } from '../types/common'
export type TargetType = 'roadmap' | 'issue' | 'comment'
export type ReportStatus = 'pending' | 'processing' | 'resolved' | 'rejected'
export interface Report {
  id: string; targetType: TargetType; targetId: string; reasonCode: string; description: string
  status: ReportStatus; resultNote: string | null; createdAt: string; handledAt: string | null
  target?: { roadmapId: string; title: string; body: string | null; visibility: string } | null
}
export async function submitReport(targetType: TargetType, targetId: string, reasonCode: string, description: string) {
  return (await http.post<ApiResponse<Report>>('/api/v1/reports', { targetType, targetId, reasonCode, description })).data.data
}
export async function reportList(admin: boolean, status: string, page: number) {
  return (await http.get<ApiResponse<Page<Report>>>('/api/v1/' + (admin ? 'admin/' : '') + 'reports', { params: { status: status || undefined, page } })).data.data
}
export async function reportDetail(id: string) {
  return (await http.get<ApiResponse<Report>>('/api/v1/admin/reports/' + id)).data.data
}
export async function handleReport(id: string, data: { expectedStatus: string; status: string; action: string; reason: string }) {
  return (await http.patch<ApiResponse<Report>>('/api/v1/admin/reports/' + id, data)).data.data
}
