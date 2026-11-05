import { http } from './http'
import type { ApiResponse, Page } from '../types/common'
import type { EnrollmentContent, EnrollmentStatus, EnrollmentSummary, LearningOverview, StudyRecord, StudyRecordPage, UpgradePreview, UpgradeRequest, UpgradeResult } from '../types/enrollment'

export async function enrollRoadmap(roadmapId: string, releaseId: string) {
  return (await http.post<ApiResponse<EnrollmentSummary>>(`/api/v1/roadmaps/${roadmapId}/enroll`, { releaseId })).data.data
}
export async function dismissUpdatePrompt(id: string, releaseId: string, dismissed: boolean) {
  return (await http.put<ApiResponse<EnrollmentSummary>>(`/api/v1/enrollments/${id}/update-prompt`, { releaseId, dismissed })).data.data
}
export async function myEnrollments(params: { status?: EnrollmentStatus; page?: number }) {
  return (await http.get<ApiResponse<Page<EnrollmentSummary>>>('/api/v1/users/me/enrollments', { params })).data.data
}
export async function enrollmentSummary(id: string, sessionId?: string) {
  return (await http.get<ApiResponse<EnrollmentSummary>>(`/api/v1/enrollments/${id}`, { params: sessionId ? { sessionId } : undefined })).data.data
}
export async function enrollmentContent(id: string, sessionId?: string) {
  return (await http.get<ApiResponse<EnrollmentContent>>(`/api/v1/enrollments/${id}/content`, { params: sessionId ? { sessionId } : undefined })).data.data
}
export async function savePosition(id: string, sessionId: string, nodeId: string) {
  return (await http.patch<ApiResponse<EnrollmentSummary>>(`/api/v1/enrollments/${id}/position`, { sessionId, nodeId })).data.data
}
export async function updateNodeStatus(id: string, sessionId: string, nodeId: string, completed: boolean) {
  return (await http.put<ApiResponse<EnrollmentSummary>>(`/api/v1/enrollments/${id}/nodes/${nodeId}/status`, { sessionId, completed })).data.data
}
export async function changeEnrollment(id: string, sessionId: string, action: 'abandon' | 'restore') {
  return (await http.post<ApiResponse<EnrollmentSummary>>(`/api/v1/enrollments/${id}/${action}`, { sessionId })).data.data
}
export async function createStudyRecord(id: string, sessionId: string) {
  return (await http.post<ApiResponse<StudyRecord>>(`/api/v1/enrollments/${id}/records`, { sessionId })).data.data
}
export async function studyRecords(id: string, page = 1) {
  return (await http.get<ApiResponse<StudyRecordPage>>(`/api/v1/enrollments/${id}/records`, { params: { page } })).data.data
}
export async function learningOverview(month?: string) {
  return (await http.get<ApiResponse<LearningOverview>>('/api/v1/users/me/learning-overview', { params: { month } })).data.data
}

export async function upgradePreview(id: string) {
  return (await http.get<ApiResponse<UpgradePreview>>(`/api/v1/enrollments/${id}/upgrade/preview`)).data.data
}
export async function upgradeLearning(id: string, data: UpgradeRequest) {
  return (await http.post<ApiResponse<UpgradeResult>>(`/api/v1/enrollments/${id}/upgrade`, data)).data.data
}
export async function learningSessions(id: string, page = 1) {
  return (await http.get<ApiResponse<Page<EnrollmentSummary>>>(`/api/v1/enrollments/${id}/sessions`, { params: { page } })).data.data
}

export async function visitResource(id: string, sessionId: string, resourceId: string) {
  await http.put(`/api/v1/enrollments/${id}/resources/${resourceId}/visit`, { sessionId })
}
