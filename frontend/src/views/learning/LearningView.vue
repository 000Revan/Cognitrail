<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { changeEnrollment, createStudyRecord, studyRecords, enrollmentContent, enrollmentSummary, savePosition, updateNodeStatus } from '../../api/enrollment'
import { ApiError } from '../../api/http'
import { dismissUpdatePrompt } from '../../api/enrollment'
import { useAuthStore } from '../../stores/auth'
import type { EnrollmentContent, EnrollmentSummary, StudyRecordPage } from '../../types/enrollment'
import RoadmapContentReader from '../../components/roadmap/RoadmapContentReader.vue'
import NodeProgressPanel from '../../components/roadmap/NodeProgressPanel.vue'
import AppDialog from '../../components/common/AppDialog.vue'
import JoinLearningDialog from '../../components/roadmap/JoinLearningDialog.vue'

const route = useRoute()
const auth = useAuthStore()
const summary = ref<EnrollmentSummary | null>(null)
const content = ref<EnrollmentContent | null>(null)
const records = ref<StudyRecordPage | null>(null)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const actionError = ref('')
const feedbackScope = ref<'node' | 'checkin' | 'route'>('route')
const confirmExit = ref(false)
const upgrading = ref(false)
async function toggleUpdatePrompt() {
  const item = summary.value
  if (!item?.currentReleaseId || busy.value) return
  const ticket = generation
  busy.value = true; feedbackScope.value = 'route'; actionError.value = ''
  try {
    const result = await dismissUpdatePrompt(item.id, item.currentReleaseId, !item.updatePromptDismissed)
    if (ticket === generation) summary.value = result
  } catch (cause) { if (ticket === generation) actionError.value = cause instanceof Error ? cause.message : '更新提示设置失败' }
  finally { if (ticket === generation) busy.value = false }
}
const requestedSession = computed(() => typeof route.query.session === 'string' ? route.query.session : undefined)
async function openUpgrade() {
  if (busy.value) return
  const ticket = generation
  await positionQueue
  if (ticket === generation && summary.value?.writable) upgrading.value = true
}
async function upgraded() { upgrading.value = false; await load() }
const resumeNode = ref<string>()
const completed = computed(() => content.value?.progress.filter(p => p.completed).map(p => p.releaseNodeId) || [])
let generation = 0
let recordGeneration = 0
let positionQueue = Promise.resolve()
let summaryRequest = 0
let dateTimer: ReturnType<typeof setTimeout> | undefined

async function loadRecords(id: string, ticket = generation) {
  const recordTicket = ++recordGeneration
  try {
    const result = await studyRecords(id)
    if (ticket !== generation || recordTicket !== recordGeneration) return
    records.value = result
    clearTimeout(dateTimer)
    // 到北京时间午夜重新查询日期，长时间停留也能继续下一天打卡。
    const nextDay = Date.parse(result.today + 'T00:00:00+08:00') + 86400000
    dateTimer = setTimeout(() => { void loadRecords(id, ticket) }, Math.min(2147483647, Math.max(1000, nextDay - Date.now() + 1000)))
  } catch (cause) { if (ticket === generation) { feedbackScope.value = 'checkin'; actionError.value = cause instanceof Error ? cause.message : '打卡状态加载失败' } }
}
async function load() {
  const ticket = ++generation
  ++recordGeneration; ++summaryRequest
  clearTimeout(dateTimer)
  summary.value = null; content.value = null; records.value = null; resumeNode.value = undefined
  loading.value = true; busy.value = false; error.value = ''; actionError.value = ''; confirmExit.value = false
  upgrading.value = false
  if (!auth.authenticated) { loading.value = false; return }
  try {
    const metadata = await enrollmentSummary(String(route.params.id), requestedSession.value)
    if (ticket !== generation) return
    summary.value = metadata
    if (metadata.contentAvailable) {
      const result = await enrollmentContent(metadata.id, requestedSession.value)
      if (ticket !== generation) return
      content.value = result; summary.value = result.enrollment
      const nodes = result.stages.flatMap(s => s.nodes)
      resumeNode.value = result.enrollment.lastNodeId || nodes[0]?.id
    }
    void loadRecords(metadata.id, ticket)
  } catch (cause) { if (ticket === generation) error.value = cause instanceof Error ? cause.message : '学习内容加载失败' }
  finally { if (ticket === generation) loading.value = false }
}
/** 位置按点击顺序串行保存，旧账号排队任务与迟到响应都丢弃。 */
function viewed(nodeId: string) {
  const item = summary.value
  if (!item?.writable) return
  const ticket = generation
  positionQueue = positionQueue.catch(() => {}).then(async () => {
    if (ticket !== generation) return
    const order = ++summaryRequest
    try {
      const result = await savePosition(item.id, item.sessionId, nodeId)
      if (ticket === generation && order === summaryRequest && summary.value) {
        summary.value.lastNodeId = result.lastNodeId; summary.value.lastOpenedAt = result.lastOpenedAt
        summary.value.progressVersion = Math.max(summary.value.progressVersion, result.progressVersion)
      }
    } catch (cause) { if (ticket === generation) handleError(cause) }
  })
}
function handleError(cause: unknown) {
  actionError.value = cause instanceof Error ? cause.message : '操作失败，请重试'
  if (cause instanceof ApiError && ['LEARNING_SESSION_CHANGED', 'ROADMAP_DISABLED', 'ENROLLMENT_ABANDONED'].includes(cause.errorCode)) {
    feedbackScope.value = 'route'
    content.value = null
    if (summary.value) summary.value.writable = false
  }
}
async function mark(nodeId: string, value: boolean) {
  const item = summary.value
  if (!item || busy.value) return
  const ticket = generation
  feedbackScope.value = 'node'
  busy.value = true; actionError.value = ''
  try {
    await positionQueue
    if (ticket !== generation) return
    ++summaryRequest
    const result = await updateNodeStatus(item.id, item.sessionId, nodeId, value)
    if (ticket !== generation || !content.value) return
    // 位置保存可能与完成响应交错；进度始终应用，位置保留较新版本。
    const latest = summary.value
    summary.value = latest && latest.progressVersion > result.progressVersion
      ? { ...result, lastNodeId: latest.lastNodeId, lastOpenedAt: latest.lastOpenedAt, progressVersion: latest.progressVersion }
      : result
    const rows = content.value.progress
    const found = rows.find(p => p.releaseNodeId === nodeId)
    if (found) found.completed = value
    else rows.push({ releaseNodeId: nodeId, completed: value, completedAt: null })
  } catch (cause) { if (ticket === generation) handleError(cause) }
  finally { if (ticket === generation) busy.value = false }
}
async function checkin() {
  const item = summary.value
  if (!item?.writable || busy.value || !records.value || records.value.checkedInToday) return
  const ticket = generation
  busy.value = true; actionError.value = ''
  feedbackScope.value = 'checkin'
  ++recordGeneration
  try {
    const result = await createStudyRecord(item.id, item.sessionId)
    if (ticket !== generation) return
    if (!result.isValid) { feedbackScope.value = 'checkin'; actionError.value = '今日打卡已被治理撤销，不能再次打卡。' }
    await loadRecords(item.id, ticket)
  } catch (cause) { if (ticket === generation) handleError(cause) }
  finally { if (ticket === generation) busy.value = false }
}
async function transition(action: 'abandon' | 'restore') {
  feedbackScope.value = 'route'
  const item = summary.value
  if (!item || busy.value) return
  const ticket = generation
  busy.value = true; actionError.value = ''
  try {
    await positionQueue
    if (ticket !== generation) return
    await changeEnrollment(item.id, item.sessionId, action)
    if (ticket === generation) await load()
  } catch (cause) { if (ticket === generation) handleError(cause) }
  finally { if (ticket === generation) busy.value = false }
}
watch([() => route.params.id, () => route.query.session, () => auth.user?.id, () => auth.sessionVersion], () => { void load() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++; clearTimeout(dateTimer) })
</script>

<template>
  <section class="roadmap-browse-page learning-content-page">
    <p class="route-breadcrumb">
      <RouterLink to="/learning">我的学习</RouterLink><span>/</span>学习路线
    </p>
    <p
      v-if="loading"
      role="status"
    >
      正在加载学习内容…
    </p>
    <p
      v-if="error"
      role="alert"
      class="form-error"
    >
      {{ error }}
    </p>
    <button
      v-if="error || actionError"
      type="button"
      class="outline-link"
      @click="load"
    >
      重新加载
    </button>
    <template v-if="summary && !loading">
      <header class="learning-compact-heading">
        <div class="route-title-line">
          <h1>{{ summary.title }}</h1><span class="version-badge">学习版 V{{ summary.versionNo }}</span>
        </div>
        <div class="route-actions">
          <RouterLink
            :to="{ name: 'learning-history', params: { id: summary.id } }"
            class="text-link"
          >打卡记录</RouterLink>
          <RouterLink
            :to="{ name: 'learning-history', params: { id: summary.id }, hash: '#version-history' }"
            class="text-link"
          >版本历史</RouterLink>
          <RouterLink
            to="/dashboard"
            class="text-link"
          >打卡日历</RouterLink>
          <button
            v-if="summary.status === 'active' && summary.isCurrentSession !== false"
            type="button"
            class="text-button"
            @click="confirmExit = true"
          >
            退出学习
          </button>
          <button
            v-else-if="summary.contentAvailable && summary.isCurrentSession !== false"
            type="button"
            class="primary-button"
            :disabled="busy"
            @click="transition('restore')"
          >
            恢复原版学习
          </button>
        </div>
      </header>
      <p
        v-if="summary.isCurrentSession === false"
        class="route-info"
      >
        这是历史学习版本，仅供回顾。<RouterLink :to="{ name: 'learning-content', params: { id: summary.id } }">返回当前学习</RouterLink>
      </p>
      <p
        v-if="summary.status === 'abandoned'"
        class="route-info"
      >
        已退出学习，位置、进度与打卡保留；恢复后继续原版。
      </p>
      <p
        v-if="!summary.contentAvailable"
        role="status"
        class="form-error"
      >
        内容已下架，正文与新增学习操作不可用，已有打卡日期保留。
      </p>
      <p
        v-if="summary.hasNewVersion && summary.isCurrentSession !== false"
        class="route-info"
      >
        <span
          v-if="summary.updatePromptDismissed"
          class="version-badge"
        >新版 V{{ summary.currentVersionNo }}</span>
        <span v-else>已有新版 V{{ summary.currentVersionNo }}，当前继续学习 V{{ summary.versionNo }}。新版不会自动替换你的学习内容。</span>
        <button
          v-if="summary.writable"
          type="button"
          class="outline-link"
          :disabled="busy"
          @click="openUpgrade"
        >
          查看版本差异
        </button>
        <button
          v-if="summary.writable"
          type="button"
          class="text-button"
          :disabled="busy"
          @click="toggleUpdatePrompt"
        >
          {{ summary.updatePromptDismissed ? '恢复更新提示' : '忽略本版提示' }}
        </button>
      </p>
      <div
        class="learning-progress"
        aria-label="主线学习进度"
      >
        <span
          class="progress-ring"
          :style="{ '--progress': summary.progressPercent + '%' }"
        >{{ summary.progressPercent }}%</span>
        <span>主线已完成 {{ summary.completedNodeCount }} / {{ summary.progressNodeCount }} 个节点</span>
      </div>
      <p
        v-if="actionError && feedbackScope === 'route' && !confirmExit"
        role="alert"
        class="form-error"
      >
        {{ actionError }}
      </p>
      <RoadmapContentReader
        v-if="content && summary.contentAvailable"
        :stages="content.stages"
        :connections="content.connections"
        :initial-node-id="resumeNode"
        learning
        :title="summary.title"
        :completed-node-ids="completed"
        :progress-completed="summary.completedNodeCount"
        :progress-total="summary.progressNodeCount"
        @view-node="viewed"
      >
        <template #actions="{ node }">
          <section class="route-checkin-panel">
            <p class="eyebrow">
              DAILY PRACTICE
            </p><h2>路线打卡</h2>
            <p class="checkin-counts">
              <strong>{{ records?.checkedInToday ? '今日已打卡' : '今日待打卡' }}</strong><span>累计 {{ records?.total ?? '—' }} 次</span>
            </p>
            <p class="field-hint">
              北京时间每天每路线一次，与节点完成独立。
            </p>
            <button
              type="button"
              class="primary-button"
              :disabled="busy || !summary.writable || !records || records.checkedInToday"
              @click="checkin"
            >
              {{ records?.checkedInToday ? '今日已打卡' : busy ? '处理中…' : '学习打卡' }}
            </button>
            <p
              v-if="actionError && feedbackScope === 'checkin'"
              role="alert"
              class="form-error"
            >
              {{ actionError }} <button
                class="text-button"
                @click="loadRecords(summary.id)"
              >
                重新加载打卡
              </button>
            </p>
          </section>
          <p
            v-if="actionError && feedbackScope === 'node'"
            role="alert"
            class="form-error"
          >
            {{ actionError }}
          </p>
          <NodeProgressPanel
            :node="node"
            :completed="!!node && completed.includes(node.id)"
            :writable="summary.writable"
            :busy="busy"
            @status="mark"
          />
        </template>
      </RoadmapContentReader>
      <AppDialog
        v-if="confirmExit"
        title="退出学习"
        @close="confirmExit = false"
      >
        <p>退出后保留位置、进度和打卡。恢复时继续原版，不清空历史。</p>
        <p
          v-if="actionError && feedbackScope === 'route'"
          role="alert"
          class="form-error"
        >
          {{ actionError }}
        </p>
        <div class="dialog-actions">
          <button
            type="button"
            class="outline-link"
            @click="confirmExit = false"
          >
            取消
          </button>
          <button
            type="button"
            class="primary-button"
            :disabled="busy"
            @click="transition('abandon')"
          >
            确认退出学习
          </button>
        </div>
      </AppDialog>
      <JoinLearningDialog
        v-if="upgrading"
        :enrollment-id="summary.id"
        @close="upgrading = false"
        @upgraded="upgraded"
      />
    </template>
  </section>
</template>

<style scoped>
.learning-progress { display: flex; align-items: center; gap: 18px; padding: 20px 0; color: var(--muted); }
.progress-ring { --progress: 0%; display: grid; place-items: center; flex-shrink: 0; width: 72px; height: 72px; border: 7px solid transparent; border-radius: 50%; background: linear-gradient(var(--paper),var(--paper)) padding-box, conic-gradient(var(--green) var(--progress), var(--line) 0) border-box; color: var(--ink); font-weight: 700; }
</style>
