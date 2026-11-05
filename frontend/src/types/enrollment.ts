import type { Connection, DetailStage } from './roadmap'

export type EnrollmentStatus = 'active' | 'abandoned'
export interface EnrollmentSummary {
  updatePromptDismissed?: boolean; currentReleaseId?: string | null
  isCurrentSession?: boolean
  id: string; roadmapId: string; sessionId: string; releaseId: string; versionNo: number
  title: string; description: string | null; difficulty: string | null
  status: EnrollmentStatus; startedAt: string; abandonedAt: string | null; completedAt: string | null
  lastNodeId: string | null; lastOpenedAt: string | null; progressVersion: number
  contentAvailable: boolean; writable: boolean; hasNewVersion: boolean; currentVersionNo: number | null
  stageCount: number; nodeCount: number; completedNodeCount: number; progressNodeCount: number; progressPercent: number
}
export interface NodeProgress { releaseNodeId: string; completed: boolean; completedAt: string | null }
export interface EnrollmentContent {
  enrollment: EnrollmentSummary; stages: DetailStage[]; connections: Connection[]; progress: NodeProgress[]
}
export interface StudyRecord {
  id: string; sessionId: string; checkinDate: string; timezoneName: string; isValid: boolean; createdAt: string
}
export interface StudyRecordPage {
  items: StudyRecord[]; total: number; today: string; checkedInToday: boolean; page: number; pageSize: number
}
export interface LearningOverview {
  learningRoadmapCount: number; completedNodeCount: number; checkinDayCount: number
  currentStreak: number; longestStreak: number; today: string; month: string; calendarDates: string[]
}
export function enrollmentStatusName(status: EnrollmentStatus) { return status === 'active' ? '学习中' : '已退出' }

export interface UpgradeNodeDifference {
  stableKey: string; sourceTitle: string | null; targetTitle: string | null
  sourceStage: string | null; targetStage: string | null; changes: string[]
  isCompleted: boolean; requiresConfirmation: boolean; targetCountsTowardProgress: boolean
  sourceExcerpt?: string | null; targetExcerpt?: string | null
}
export interface UpgradePreview {
  sourceSessionId: string; targetReleaseId: string; sourceVersionNo: number; targetVersionNo: number
  progressVersion: number; updateSummary: string; sourceCompleted: number; sourceTotal: number; sourcePercent: number
  targetTotal: number; completedMin: number; completedMax: number; percentMin: number; percentMax: number
  nodeChanges: UpgradeNodeDifference[]
  stageChanges: { stableKey: string; sourceTitle: string | null; targetTitle: string | null; changes: string[] }[]
  releaseChanges: string[]; connectionsChanged: boolean
}
export interface UpgradeRequest {
  sourceSessionId: string; targetReleaseId: string; progressVersion: number; requestKey: string
  confirmations: { stableKey: string; action: 'keep' | 'relearn' }[]
}
export interface UpgradeResult {
  sourceSessionId: string; targetSessionId: string; targetReleaseId: string; versionNo: number
  progressVersion: number; completedNodeCount: number; progressNodeCount: number; progressPercent: number; lastNodeId: string | null
}
