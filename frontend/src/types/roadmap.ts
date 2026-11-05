import type { EntityId } from './common'

export interface Connection { source: string; target: string }
export interface ResourceInput {
  languageCode?: string | null; accessType?: 'free' | 'paid' | 'freemium' | 'unknown'
  id: string; title: string; resourceType: 'article' | 'video' | 'document' | 'book' | 'course' | 'other'; resourceUrl: string
}
export interface NodeInput {
  stableKey?: string | null; revisionNo?: number | null
  isOptional?: boolean; countsTowardProgress?: boolean; changePolicy?: 'retain' | 'reconfirm'
  id: string; title: string; content: string; estimatedMinutes: number | null; tips: string | null
  canvasX: number; canvasY: number; resources: ResourceInput[]
}
export interface StageInput {
  stableKey?: string | null
  id: string; title: string; description: string | null; canvasX: number; canvasY: number; nodes: NodeInput[]
}
export interface RoadmapDocument {
  effortNote?: string | null; licenseCode?: 'UNSPECIFIED' | 'UNLICENSED' | 'CC-BY-4.0' | 'CC-BY-SA-4.0' | 'custom'; licenseUrl?: string | null
  expectedVersion: number; title: string; description: string | null
  difficulty: 'beginner' | 'intermediate' | 'advanced'; coverUrl: string | null
  stages: StageInput[]; connections: Connection[]
}
export interface GraphNode { id: string; title: string; canvasX: number; canvasY: number }
export interface GraphStage {
  id: string; title: string; canvasX: number; canvasY: number; nodes: GraphNode[]
}
export interface RoadmapSummary {
  effortNote?: string | null; licenseCode?: string; licenseUrl?: string | null
  publishedTitle?: string | null; hasUnpublishedChanges?: boolean
  learnerCount?: number; favoriteCount?: number
  roadmapType?: 'user' | 'official'; canMaintain?: boolean; canManageOfficial?: boolean
  disabledAt?: string | null; disabledBy?: string | null
  id: EntityId; title: string; description: string | null; difficulty: string; coverUrl: string | null
  status: 'draft' | 'withdrawn' | 'published' | 'archived' | 'disabled'; displayStatus: string
  editVersion: number; stageCount: number; nodeCount: number; updatedAt: string
  publishedAt: string | null; releaseId: string | null; versionNo: number | null
  authorArchivedAt: string | null; isOwner: boolean; canDelete: boolean; disabledReason: string | null
  canFavorite: boolean; canStartLearning: boolean
  author: { id: EntityId; username: string; nickname: string | null; avatarUrl?: string | null; bio?: string | null }
}
export interface DetailNode extends GraphNode {
  isOptional?: boolean; countsTowardProgress?: boolean
  content?: string; estimatedMinutes?: number | null; tips?: string | null; resources?: ResourceInput[]
}
export interface DetailStage extends GraphStage { description?: string | null; nodes: DetailNode[] }
export interface RoadmapDetail extends RoadmapSummary {
  moderationHistory?: { id: string; action: string; reason: string; actorId: string; createdAt: string }[]
  updateSummary?: string | null
  releases?: { id: string; versionNo: number; title: string; publishedAt: string }[]
  learning?: { id: string; status: 'active' | 'abandoned' } | null
  learnerCount: number; favoriteCount: number; isFavorited: boolean
  stages: DetailStage[]; connections: Connection[]; canReadContent: boolean
  contentSource: 'published' | 'draft' | null
}

export interface PublicRoadmap {
  id: EntityId; title: string; description: string | null; difficulty: string; coverUrl: string | null
  roadmapType: 'user' | 'official'; releaseId: EntityId; versionNo: number; publishedAt: string
  stageCount: number; nodeCount: number; learnerCount: number; favoriteCount: number
  isFavorited: boolean; isOwner: boolean
  author: { id: EntityId; username: string; nickname: string | null; avatarUrl?: string | null; bio?: string | null }
}
export interface FavoriteItem {
  roadmapId: EntityId; title: string; status: RoadmapSummary['status']; accessible: boolean
  favoritedAt: string; roadmap: PublicRoadmap | null
}
export interface DraftResponse {
  id: EntityId; status: RoadmapSummary['status']; authorArchivedAt: string | null
  document: RoadmapDocument; idMap?: Record<string, string>
}
export interface PublicationIssue {
  message: string; field: string; stageId?: string; nodeId?: string; resourceId?: string
}
