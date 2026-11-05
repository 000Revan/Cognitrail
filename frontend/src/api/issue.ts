import { http } from './http'
import type { ApiResponse, Page } from '../types/common'

export type IssueStatus = 'open' | 'resolved' | 'closed'
export interface DiscussionAuthor { id: string; nickname: string; username?: string; avatarUrl?: string | null }
export interface Issue {
  id: string; roadmapId: string; roadmapCreatorId?: string; title: string; body: string | null; status: IssueStatus
  visibility: string; author: DiscussionAuthor | null; commentCount?: number
  createdAt: string; updatedAt: string; lastActivityAt: string
  canEdit: boolean; canResolve: boolean; canClose: boolean
}
export interface Comment {
  id: string; body: string | null; replyToCommentId: string | null; visibility: string
  author: DiscussionAuthor | null; replyToAuthor?: DiscussionAuthor | null
  replies?: Page<Comment>; canEdit: boolean; createdAt: string; updatedAt: string
}
export interface IssueDetail extends Issue {
  subscribed: boolean; comments: Page<Comment>; roadmapTitle?: string
  events: { id: string; type: string; fromStatus: IssueStatus | null; toStatus: IssueStatus | null; reason: string | null; createdAt: string }[]
}
export function issueUrl(roadmap: string, issue?: string) {
  return `/api/v1/roadmaps/${encodeURIComponent(roadmap)}/issues${issue ? '/' + encodeURIComponent(issue) : ''}`
}
export interface IssuePage extends Page<Issue> { topicCount: number; closedCount: number; roadmapTitle: string }
export async function listIssues(roadmap: string, params: { page: number; status?: IssueStatus; sortBy?: string; order?: string }) {
  return (await http.get<ApiResponse<IssuePage>>(issueUrl(roadmap), { params })).data.data
}
export async function getReplies(roadmap: string, issue: string, rootId: string, page: number) {
  return (await http.get<ApiResponse<Page<Comment>>>(issueUrl(roadmap, issue) + '/comments/' + encodeURIComponent(rootId) + '/replies', { params: { page } })).data.data
}
export async function getIssue(roadmap: string, issue: string, params: { page: number; commentId?: string }) {
  return (await http.get<ApiResponse<IssueDetail>>(issueUrl(roadmap, issue), { params })).data.data
}
export async function createIssue(roadmap: string, title: string, body: string) {
  return (await http.post<ApiResponse<Issue>>(issueUrl(roadmap), { title, body })).data.data
}
export async function issueAction(roadmap: string, issue: string, action: string, data?: unknown, method: 'post' | 'patch' | 'put' | 'delete' = 'post') {
  return (await http.request<ApiResponse<{ id: string; commentId?: string }>>({ url: issueUrl(roadmap, issue) + action, method, data })).data.data
}
