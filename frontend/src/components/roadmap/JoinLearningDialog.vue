<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { enrollRoadmap, upgradeLearning, upgradePreview } from '../../api/enrollment'
import { ApiError } from '../../api/http'
import type { EnrollmentSummary, UpgradePreview, UpgradeRequest } from '../../types/enrollment'
import AppDialog from '../common/AppDialog.vue'
const props = defineProps<{ roadmapId?: string; releaseId?: string; versionNo?: number; enrollmentId?: string }>()
const emit = defineEmits<{ close: []; refresh: []; done: [value: EnrollmentSummary]; upgraded: [] }>()
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const preview = ref<UpgradePreview | null>(null)
const choices = ref<Record<string, '' | 'keep' | 'relearn'>>({})
const pending = ref<UpgradeRequest | null>(null)
const expired = ref(false)
const required = computed(() => preview.value?.nodeChanges.filter(row => row.requiresConfirmation) || [])
const unanswered = computed(() => required.value.some(row => !choices.value[row.stableKey]))
const predicted = computed(() => (preview.value?.completedMin || 0) + required.value.filter(row => choices.value[row.stableKey] === 'keep' && row.targetCountsTowardProgress).length)
const percent = computed(() => preview.value?.targetTotal ? Math.floor(predicted.value * 100 / preview.value.targetTotal) : 0)
let generation = 0
let disposed = false
function close() {
  // 请求已发出但响应丢失时不能声称取消，刷新当前学习以核对服务端结果。
  if (pending.value) emit('upgraded')
  else emit('close')
}
onBeforeUnmount(() => { disposed = true; generation++ })
const labels: Record<string, string> = {
  added: '新增', removed: '删除', renamed: '改名', content: '内容调整', tips: '提示调整',
  time: '参考时间调整', resources: '资源替换', optional: '可选属性变化', progress: '进度计入变化',
  moved: '移动阶段', order: '目录顺序变化', semantic: '学习要求变化', layout: '画布位置变化',
  title: '标题变化', description: '说明变化', position: '顺序变化', canvas_x: '位置变化', canvas_y: '位置变化',
  summary: '路线简介', difficulty: '难度', effort_note: '参考投入', license_code: '许可', license_url: '许可链接',
}
function changeNames(values: string[]) { return [...new Set(values.map(value => labels[value] || value))].join('、') }
async function refreshPreview() {
  if (!props.enrollmentId || busy.value) return
  const ticket = ++generation
  loading.value = true; preview.value = null; choices.value = {}; pending.value = null; expired.value = false; error.value = ''
  try {
    const result = await upgradePreview(props.enrollmentId)
    if (!disposed && ticket === generation) {
      preview.value = result
      choices.value = Object.fromEntries(result.nodeChanges.filter(row => row.requiresConfirmation).map(row => [row.stableKey, '' as const]))
    }
  } catch (cause) {
    if (disposed || ticket !== generation) return
    if (cause instanceof ApiError && cause.errorCode === 'UPGRADE_NOT_AVAILABLE') emit('upgraded')
    else error.value = cause instanceof Error ? cause.message : '差异加载失败，请重试'
  } finally { if (!disposed && ticket === generation) loading.value = false }
}
async function submit() {
  if (busy.value) return
  if (props.enrollmentId && (!preview.value || unanswered.value || expired.value)) return
  const ticket = generation
  busy.value = true; error.value = ''
  try {
    if (props.enrollmentId && preview.value) {
      // 响应丢失后冻结选择，沿用完全相同的请求键和语义重试。
      pending.value ??= {
        sourceSessionId: preview.value.sourceSessionId, targetReleaseId: preview.value.targetReleaseId,
        progressVersion: preview.value.progressVersion, requestKey: crypto.randomUUID(),
        confirmations: required.value.map(row => ({ stableKey: row.stableKey, action: choices.value[row.stableKey] as 'keep' | 'relearn' })),
      }
      await upgradeLearning(props.enrollmentId, pending.value)
      if (!disposed && ticket === generation) emit('upgraded')
    } else if (props.roadmapId && props.releaseId) {
      const result = await enrollRoadmap(props.roadmapId, props.releaseId)
      if (!disposed && ticket === generation) emit('done', result)
    }
  } catch (cause) {
    if (disposed || ticket !== generation) return
    error.value = cause instanceof Error ? cause.message : '操作失败，请重试'
    if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500) pending.value = null
    if (cause instanceof ApiError && cause.status === 409) expired.value = true
  } finally { if (!disposed && ticket === generation) busy.value = false }
}
onMounted(() => { if (props.enrollmentId) void refreshPreview() })
</script>
<template>
  <AppDialog
    class="learning-action-dialog"
    :title="enrollmentId ? '版本差异与升级确认' : '开始学习'"
    :busy="busy"
    @close="close"
  >
    <div
      v-if="enrollmentId"
      class="upgrade-preview"
    >
      <p
        v-if="loading"
        role="status"
      >
        正在比较学习版本…
      </p>
      <template v-if="preview">
        <h3>V{{ preview.sourceVersionNo }} → V{{ preview.targetVersionNo }}</h3>
        <p class="update-summary">
          {{ preview.updateSummary }}
        </p>
        <div
          class="upgrade-progress"
          aria-label="升级进度影响"
        >
          <p>当前：{{ preview.sourceCompleted }} / {{ preview.sourceTotal }} · {{ preview.sourcePercent }}%</p>
          <p v-if="unanswered">
            新版可保留 {{ preview.completedMin }}—{{ preview.completedMax }} / {{ preview.targetTotal }} · {{ preview.percentMin }}%—{{ preview.percentMax }}%，请先完成选择。
          </p>
          <p v-else>
            升级后：{{ predicted }} / {{ preview.targetTotal }} · {{ percent }}%
          </p>
        </div>
        <p>未确认前继续原版。升级会保留旧版只读历史，收藏和当日打卡资格保持。</p>
        <p v-if="preview.releaseChanges.length">
          路线调整：{{ changeNames(preview.releaseChanges) }}
        </p>
        <p v-if="preview.connectionsChanged">
          阶段连接关系已调整。
        </p>
        <ul
          v-if="preview.stageChanges.length"
          class="upgrade-stage-list"
          aria-label="阶段差异"
        >
          <li
            v-for="row in preview.stageChanges"
            :key="row.stableKey"
          >
            {{ row.sourceTitle || '无' }} → {{ row.targetTitle || '已删除' }}：{{ changeNames(row.changes) }}
          </li>
        </ul>
        <ul
          class="upgrade-node-list"
          aria-label="节点差异"
        >
          <li
            v-for="row in preview.nodeChanges"
            :key="row.stableKey"
          >
            <strong>{{ row.targetTitle || row.sourceTitle }}</strong>
            <p v-if="row.changes.includes('renamed')">
              原名：{{ row.sourceTitle }}
            </p>
            <p>{{ changeNames(row.changes) }}<span v-if="row.isCompleted"> · 原版已完成</span></p>
            <p v-if="row.changes.includes('moved')">
              {{ row.sourceStage }} → {{ row.targetStage }}
            </p>
            <details
              v-if="row.sourceExcerpt != null || row.targetExcerpt != null"
              :open="row.requiresConfirmation"
              class="upgrade-excerpts"
            >
              <summary>查看学习要求变化</summary>
              <p><strong>原版：</strong>{{ row.sourceExcerpt || '未提供' }}</p>
              <p><strong>新版：</strong>{{ row.targetExcerpt || '未提供' }}</p>
              <small>各展示前1000字；历史版本完整内容保留供回顾。</small>
            </details>
            <label v-if="row.requiresConfirmation">
              学习要求已变化，请明确选择
              <select
                v-model="choices[row.stableKey]"
                :aria-label="'任务确认：' + row.targetTitle"
                :disabled="busy || !!pending"
              >
                <option value="">请选择</option><option value="keep">保留完成</option><option value="relearn">重新学习</option>
              </select>
            </label>
          </li>
        </ul>
        <p v-if="!preview.nodeChanges.length">
          学习节点没有变化。
        </p>
        <p class="field-hint">
          进度比例可能因主线节点增减而变化。语义变化的已完成节点由你决定保留或重学。
        </p>
      </template>
    </div>
    <p v-else>
      开始学习 V{{ versionNo }}，初始进度为 0。浏览、完成节点和打卡分别记录。
    </p>
    <p
      v-if="error"
      role="alert"
      class="form-error"
    >
      {{ error }}
      <button
        v-if="!enrollmentId"
        type="button"
        class="text-button"
        @click="emit('refresh')"
      >
        刷新路线
      </button>
    </p>
    <template #footer>
      <button
        type="button"
        class="outline-link"
        :disabled="busy"
        @click="close"
      >
        {{ enrollmentId ? pending ? '关闭并刷新' : '暂不升级' : '取消' }}
      </button>
      <button
        v-if="enrollmentId && error"
        type="button"
        class="outline-link"
        :disabled="busy"
        @click="refreshPreview"
      >
        重新查看差异
      </button>
      <button
        type="button"
        class="primary-button"
        :disabled="busy || loading || !!enrollmentId && (!preview || unanswered || expired)"
        @click="submit"
      >
        {{ busy ? '处理中…' : enrollmentId ? pending ? '重试本次升级' : '确认升级' : '确认开始学习' }}
      </button>
    </template>
  </AppDialog>
</template>
<style scoped>
.learning-action-dialog[open] { display: flex; flex-direction: column; width: min(900px, calc(100vw - 32px)); max-height: calc(100vh - 32px); max-height: calc(100dvh - 32px); }
.learning-action-dialog :deep(.dialog-body) { min-height: 0; overflow: auto; }
.learning-action-dialog :deep(header), .learning-action-dialog :deep(footer) { flex-shrink: 0; }
.learning-action-dialog :deep(footer) { flex-wrap: wrap; }
.upgrade-preview { max-width: 680px; min-width: 0; }
.update-summary { white-space: pre-wrap; overflow-wrap: anywhere; }
.upgrade-progress { padding: 12px 16px; border: 1px solid var(--line); border-radius: 8px; background: var(--green-light, #f4f8f6); }
.upgrade-node-list { padding: 0; list-style: none; }
.upgrade-node-list li { border-top: 1px solid var(--line); padding: 16px 0; overflow-wrap: anywhere; }
.upgrade-node-list p { margin: 8px 0; color: var(--muted); }
.upgrade-node-list select { display: block; width: 100%; margin-top: 8px; min-height: 42px; }
.upgrade-stage-list { padding-left: 20px; line-height: 1.8; }
.upgrade-excerpts { margin: 12px 0; padding: 12px; background: var(--green-light, #f4f8f6); border-radius: 8px; }
.upgrade-excerpts p { white-space: pre-wrap; }
</style>
