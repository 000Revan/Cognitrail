import { http } from './http'
import type { ApiResponse, Page } from '../types/common'
import type { DraftResponse, FavoriteItem, PublicationIssue, PublicRoadmap, RoadmapDetail, RoadmapDocument, RoadmapSummary } from '../types/roadmap'

export async function publicRoadmaps(params: { q?: string; difficulty?: string; page?: number; pageSize?: number; sortBy?: string; order?: string }) {
  return (await http.get<ApiResponse<Page<PublicRoadmap>>>('/api/v1/roadmaps', { params })).data.data
}
export async function myFavorites(params: { page?: number; pageSize?: number }) {
  return (await http.get<ApiResponse<Page<FavoriteItem>>>('/api/v1/users/me/favorites', { params })).data.data
}
export async function changeFavorite(id: string, enabled: boolean) {
  const url = '/api/v1/roadmaps/' + id + '/favorite'
  const response = enabled ? await http.put<ApiResponse<{ roadmapId: string; isFavorited: boolean; favoriteCount: number }>>(url)
    : await http.delete<ApiResponse<{ roadmapId: string; isFavorited: boolean; favoriteCount: number }>>(url)
  return response.data.data
}

export async function myRoadmaps(params: { archived: boolean; state?: string; q?: string; page?: number; pageSize?: number }) {
  return (await http.get<ApiResponse<Page<RoadmapSummary>>>('/api/v1/roadmaps/mine', { params })).data.data
}
export async function createRoadmap(title: string, official = false) {
  return (await http.post<ApiResponse<{ id: string }>>('/api/v1/roadmaps', { title, roadmapType: official ? 'official' : 'user' })).data.data
}
export async function adminRoadmaps(params: { officialOnly?: boolean; archived?: boolean; status?: string; keyword?: string; difficulty?: string; sortBy?: string; order?: string; page?: number }) {
  const url = params.officialOnly ? '/api/v1/admin/official-roadmaps' : '/api/v1/admin/roadmaps'
  return (await http.get<ApiResponse<Page<RoadmapSummary>>>(url, { params })).data.data
}
export async function adminRoadmapDetail(id: string, releaseId?: string) {
  return (await http.get<ApiResponse<RoadmapDetail>>('/api/v1/admin/roadmaps/' + id, { params: { releaseId } })).data.data
}
export async function disableRoadmap(id: string, expectedVersion: number, reason: string) {
  return (await http.post<ApiResponse<{ id: string; status: string; disabledReason: string }>>(
    '/api/v1/admin/roadmaps/' + id + '/disable', { expectedVersion, reason })).data.data
}
export async function restoreRoadmap(id: string, expectedVersion: number, reason: string) {
  return (await http.post<ApiResponse<{ id: string; status: string }>>('/api/v1/admin/roadmaps/' + id + '/restore', { expectedVersion, reason })).data.data
}
export async function roadmapDetail(id: string, enrollmentId?: string, preview?: 'draft') {
  return (await http.get<ApiResponse<RoadmapDetail>>('/api/v1/roadmaps/' + id, { params: { enrollmentId, preview } })).data.data
}
export async function roadmapDraft(id: string) {
  return (await http.get<ApiResponse<DraftResponse>>('/api/v1/roadmaps/' + id + '/draft')).data.data
}
export async function saveRoadmap(id: string, data: RoadmapDocument) {
  return (await http.put<ApiResponse<DraftResponse>>('/api/v1/roadmaps/' + id + '/draft', data)).data.data
}
export async function validateRoadmap(id: string, expectedVersion: number) {
  return (await http.post<ApiResponse<{ issues: PublicationIssue[]; nextVersionNo: number }>>(
    '/api/v1/roadmaps/' + id + '/validate', { expectedVersion })).data.data
}
export async function publishRoadmap(id: string, expectedVersion: number, updateSummary: string) {
  return (await http.post<ApiResponse<{ versionNo: number }>>(
    '/api/v1/roadmaps/' + id + '/publish', { expectedVersion, updateSummary })).data.data
}
export async function changeRoadmap(id: string, expectedVersion: number, action: 'withdraw' | 'archive' | 'restore' | 'delete') {
  const url = '/api/v1/roadmaps/' + id
  if (action === 'delete') return http.delete(url, { data: { expectedVersion } })
  return http.post(url + '/' + action, { expectedVersion })
}
