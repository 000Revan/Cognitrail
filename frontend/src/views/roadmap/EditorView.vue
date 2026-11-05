<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { publishRoadmap, roadmapDraft, saveRoadmap, validateRoadmap } from '../../api/roadmap'
import { ApiError } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import type { PublicationIssue, RoadmapDocument } from '../../types/roadmap'
import { cleanDocument, newNode, newStage, publicationIssues, temporaryId } from '../../domain/roadmap'
import RoadmapCanvas from '../../components/roadmap/RoadmapCanvas.vue'
import AppDialog from '../../components/common/AppDialog.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
let request = 0
const document = ref<RoadmapDocument | null>(null)
const baseline = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')
function notify(message: string, type: 'success' | 'warning' = 'warning') { ElMessage.closeAll(); ElMessage({ message, type, duration: 3000, showClose: true, placement: 'bottom' }) }
const conflict = ref(false)
const kind = ref<'basic' | 'stage' | 'node'>('basic')
const selectedId = ref('')
const selectedStageId = ref('')
const inspectorOpen = ref(true)
const contextMenu = ref<{ kind: 'stage' | 'node'; id: string; stageId: string; x: number; y: number } | null>(null)
const deleteConfirm = ref(false)
const resetConfirm = ref(false)
const checkOpen = ref(false)
const preview = ref(false)
const nextVersion = ref(1)
const updateSummary = ref('')
const serverIssues = ref<PublicationIssue[]>([])
const serverCheckedDocument = ref('')
const issues = computed(() => {
  if (!document.value) return []
  const local = publicationIssues(document.value)
  return local.length ? local : serverCheckedDocument.value === cleanDocument(document.value) ? serverIssues.value : []
})
const stage = computed(() => document.value?.stages.find(s => s.id === selectedStageId.value))
const node = computed(() => stage.value?.nodes.find(n => n.id === selectedId.value))
const orderedComponents = computed(() => kind.value === 'stage' ? document.value?.stages : kind.value === 'node' ? stage.value?.nodes : [])
const selectedIndex = computed(() => orderedComponents.value?.findIndex(item => item.id === selectedId.value) ?? -1)
const isDirty = computed(() => !!document.value && cleanDocument(document.value) !== baseline.value)
const nodeCount = computed(() => document.value?.stages.reduce((n, s) => n + s.nodes.length, 0) || 0)
const history = ref<string[]>([])
let historyTimer: ReturnType<typeof setTimeout> | undefined
let historyPaused = false

/** 历史只在编辑器会话保留，保存后以服务端映射后的ID建立新基线。 */
function captureHistory() {
  clearTimeout(historyTimer)
  if (!document.value || historyPaused) return
  const value = cleanDocument(document.value)
  if (history.value.at(-1) !== value) {
    history.value.push(value); history.value = history.value.slice(-40)
  }
}
watch(document, () => {
  if (historyPaused || !document.value) return
  clearTimeout(historyTimer)
  historyTimer = setTimeout(captureHistory, 350)
}, { deep: true })
function setDocument(value: RoadmapDocument) {
  clearTimeout(historyTimer); historyPaused = true
  document.value = value; baseline.value = cleanDocument(value)
  history.value = [baseline.value]; serverIssues.value = []; serverCheckedDocument.value = ''
  void nextTick(() => { historyPaused = false })
}
async function load() {
  if (busy.value) return
  if (isDirty.value && !window.confirm('重新加载将丢弃未保存的修改，是否继续？')) return
  const ticket = ++request
  loading.value = true; error.value = ''; conflict.value = false; contextMenu.value = null
  try {
    const result = await roadmapDraft(String(route.params.id))
    if (ticket !== request) return
    if (!['draft', 'published'].includes(result.status) || result.authorArchivedAt) {
      document.value = null
      throw new Error('此路线当前不能编辑，请先恢复已归档路线。')
    }
    setDocument(result.document)
  } catch (cause) { if (ticket === request) error.value = cause instanceof Error ? cause.message : '工作稿加载失败' }
  finally { if (ticket === request) loading.value = false }
}
function select(value: 'stage' | 'node', id: string, stageId: string) {
  kind.value = value; selectedId.value = id; selectedStageId.value = stageId; contextMenu.value = null; inspectorOpen.value = true
}
function addStage(x?: number, y?: number) {
  if (!document.value || busy.value || document.value.stages.length >= 40) return
  const index = document.value.stages.length
  const item = newStage(x ?? 60 + (index % 3) * 440, y ?? 60 + Math.floor(index / 3) * 360)
  document.value.stages.push(item); select('stage', item.id, item.id)
}
function addNode(stageId?: string, x?: number, y?: number) {
  if (!document.value || busy.value) return
  const target = document.value.stages.find(s => s.id === (stageId || selectedStageId.value)) || document.value.stages.at(-1)
  if (!target) { notify('请先创建一个阶段，再添加节点。'); return }
  if (target.nodes.length >= 80 || nodeCount.value >= 500) { notify('已达到节点数量上限。'); return }
  const item = newNode(target.nodes.length)
  if (x !== undefined) item.canvasX = x
  if (y !== undefined) item.canvasY = y
  target.nodes.push(item); select('node', item.id, target.id)
}
function move(value: 'stage' | 'node', id: string, x: number, y: number) {
  if (!document.value || busy.value) return
  const item = value === 'stage' ? document.value.stages.find(s => s.id === id)
    : document.value.stages.flatMap(s => s.nodes).find(n => n.id === id)
  if (item) { item.canvasX = x; item.canvasY = y }
}
function connect(source: string, target: string) {
  if (!document.value || busy.value || source === target) return
  if (document.value.connections.some(e => e.source === source && e.target === target)) {
    notify('这两个阶段之间已存在相同方向的连线。'); return
  }
  if (document.value.connections.length >= 200) { notify('最多添加200条阶段连线。'); return }
  document.value.connections.push({ source, target })
}
function removeConnection(index: number) { if (!busy.value) document.value?.connections.splice(index, 1) }
function showContext(value: 'stage' | 'node', id: string, stageId: string, x: number, y: number) {
  if (busy.value) return
  // 菜单目标独立保存，右键本身不切换正在编辑的组件。
  contextMenu.value = { kind: value, id, stageId, x: Math.min(x, window.innerWidth - 170), y: Math.min(y, window.innerHeight - 140) }
  void nextTick(() => window.document.querySelector<HTMLButtonElement>('.editor-context-menu button')?.focus())
}
function contextAction(action: 'edit' | 'delete') {
  const target = contextMenu.value
  if (!target || busy.value) return
  select(target.kind, target.id, target.stageId)
  if (action === 'delete') deleteConfirm.value = true
  else void nextTick(() => window.document.querySelector<HTMLInputElement>('#' + target.kind + '-title')?.focus())
}
function contextKeys(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    contextMenu.value = null
    event.preventDefault()
  } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    const buttons = [...window.document.querySelectorAll<HTMLButtonElement>('.editor-context-menu button')]
    const index = buttons.indexOf(window.document.activeElement as HTMLButtonElement)
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
      : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length
    buttons[next]?.focus(); event.preventDefault()
  }
}
function deleteComponent() {
  if (!document.value || busy.value) return
  if (kind.value === 'stage') {
    document.value.stages = document.value.stages.filter(s => s.id !== selectedId.value)
    document.value.connections = document.value.connections.filter(e => e.source !== selectedId.value && e.target !== selectedId.value)
  } else if (stage.value) stage.value.nodes = stage.value.nodes.filter(n => n.id !== selectedId.value)
  deleteConfirm.value = false; contextMenu.value = null; kind.value = 'basic'; selectedId.value = ''; selectedStageId.value = ''
}
function shift(direction: number) {
  if (!document.value || busy.value || ![-1, 1].includes(direction)) return
  const list = orderedComponents.value
  if (!list) return
  const index = list.findIndex(item => item.id === selectedId.value)
  if (index < 0 || index + direction < 0 || index + direction >= list.length) return
  const moving = list[index]!
  const neighbor = list[index + direction]!
  // 同时交换目录顺序和画布位置，保留组件ID及其内容、资源与选中状态。
  const { canvasX, canvasY } = moving
  moving.canvasX = neighbor.canvasX; moving.canvasY = neighbor.canvasY
  neighbor.canvasX = canvasX; neighbor.canvasY = canvasY
  const [item] = list.splice(index, 1)
  if (item) list.splice(index + direction, 0, item as never)
}
function changeNodeStage(event: Event) {
  if (!node.value || !stage.value || !document.value) return
  const target = document.value.stages.find(s => s.id === (event.target as HTMLSelectElement).value)
  if (!target || target.id === stage.value.id) return
  const moving = node.value
  stage.value.nodes = stage.value.nodes.filter(n => n.id !== moving.id)
  moving.canvasX = 24; moving.canvasY = 72 + target.nodes.length * 72
  target.nodes.push(moving); selectedStageId.value = target.id
}
function addResource() {
  if (!node.value || node.value.resources.length >= 30) return
  node.value.resources.push({ id: temporaryId(), title: '', resourceType: 'article', resourceUrl: '' })
}
function referenceTime(event: Event) {
  if (node.value) node.value.estimatedMinutes = (event.target as HTMLInputElement).checked ? 60 : null
}
function setMinutes(event: Event) {
  if (!node.value) return
  const value = (event.target as HTMLInputElement).value
  node.value.estimatedMinutes = value === '' ? null : Number(value)
}
function dragComponent(event: DragEvent, component: string) {
  event.dataTransfer?.setData('application/x-cognitrail-component', component)
}
function undo() {
  if (busy.value) return
  captureHistory()
  if (history.value.length < 2) return
  historyPaused = true
  history.value.pop()
  document.value = JSON.parse(history.value.at(-1)!) as RoadmapDocument
  kind.value = 'basic'; selectedId.value = selectedStageId.value = ''; contextMenu.value = null
  void nextTick(() => { historyPaused = false })
}
function resetCanvas() {
  if (busy.value || !document.value) return
  captureHistory()
  document.value.stages = []; document.value.connections = []
  kind.value = 'basic'; selectedId.value = selectedStageId.value = ''; contextMenu.value = null
  resetConfirm.value = false; serverIssues.value = []; serverCheckedDocument.value = ''
  captureHistory()
  void nextTick(() => window.document.getElementById('editor-undo')?.focus())
}
function report(cause: unknown) {
  error.value = cause instanceof Error ? cause.message : '请求失败，请重试'
  if (cause instanceof ApiError) {
    conflict.value = cause.errorCode === 'EDIT_VERSION_CONFLICT'
    const details = cause.details as { issues?: PublicationIssue[]; details?: { issues?: PublicationIssue[] } } | undefined
    if (details?.issues || details?.details?.issues) {
      serverIssues.value = details.issues || details.details!.issues!
      serverCheckedDocument.value = document.value ? cleanDocument(document.value) : ''
      preview.value = false; checkOpen.value = true
    }
    if (Array.isArray(cause.details)) {
      const fields = cause.details as { message?: string; path?: (string | number)[] }[]
      error.value += '：' + fields.slice(0, 3).map(item => item.message || item.path?.join('.') || '请检查字段').join('；')
    }
  }
}
async function persist() {
  if (!document.value) return false
  const ticket = request
  const result = await saveRoadmap(String(route.params.id), document.value)
  if (ticket !== request) return false
  const nextSelected = result.idMap?.[selectedId.value] || selectedId.value
  const nextStage = result.idMap?.[selectedStageId.value] || selectedStageId.value
  setDocument(result.document)
  selectedId.value = nextSelected; selectedStageId.value = nextStage
  conflict.value = false; return true
}
async function save() {
  if (busy.value || !document.value) return
  busy.value = true; error.value = ''
  try { if (await persist()) notify('工作稿已保存。', 'success') }
  catch (cause) { report(cause) }
  finally { busy.value = false }
}
async function previewPublication() {
  if (busy.value || !document.value) return
  if (issues.value.length) { await openChecks(); return }
  const ticket = request
  busy.value = true; error.value = ''
  try {
    if (isDirty.value && !await persist()) return
    const result = await validateRoadmap(String(route.params.id), document.value.expectedVersion)
    if (ticket !== request) return
    serverIssues.value = result.issues; serverCheckedDocument.value = cleanDocument(document.value)
    nextVersion.value = result.nextVersionNo
    if (result.issues.length) { await openChecks(); return }
    checkOpen.value = false; preview.value = true
  } catch (cause) { if (ticket === request) report(cause) }
  finally { if (ticket === request) busy.value = false }
}
async function openChecks() {
  checkOpen.value = true
  await nextTick(); window.document.getElementById('publication-check-list')?.focus()
}
function closeChecks() { checkOpen.value = false; window.document.getElementById('publication-check-toggle')?.focus() }
function issueContext(issue: PublicationIssue) {
  const stage = document.value?.stages.find(s => s.id === issue.stageId)
  const node = stage?.nodes.find(n => n.id === issue.nodeId)
  const resource = node?.resources.find(r => r.id === issue.resourceId)
  return [stage?.title, node?.title, resource?.title].filter(Boolean).join(' / ') || '基本信息'
}
async function locate(issue: PublicationIssue) {
  preview.value = false; checkOpen.value = false
  inspectorOpen.value = true
  if (issue.nodeId && issue.stageId) select('node', issue.nodeId, issue.stageId)
  else if (issue.stageId) select('stage', issue.stageId, issue.stageId)
  else kind.value = 'basic'
  await nextTick()
  const basic: Record<string, string> = { title: 'route-title', description: 'route-description', effortNote: 'effort-note', stages: document.value?.stages.length ? 'add-node' : 'add-stage' }
  const stageFields: Record<string, string> = { title: 'stage-title', description: 'stage-description', canvasX: 'stage-x', canvasY: 'stage-y', nodes: 'add-node' }
  const nodeFields: Record<string, string> = { title: 'node-title', content: 'node-content', tips: 'node-tips', resources: 'add-node-resource', isOptional: 'node-purpose' }
  const resourceFields: Record<string, string> = { title: 'resource-title-', resourceUrl: 'resource-url-', resourceType: 'resource-type-' }
  let target = issue.resourceId ? window.document.getElementById((resourceFields[issue.field] || 'resource-title-') + issue.resourceId)
    : window.document.getElementById((issue.nodeId ? nodeFields : issue.stageId ? stageFields : basic)[issue.field] || '')
  if (!target && issue.field === 'estimatedMinutes') target = window.document.querySelector('[aria-label="预计学习分钟"]')
  if (!target && issue.field === 'connections') target = window.document.querySelector('[aria-label="连线目标阶段"]')
  target ??= window.document.querySelector('.editor-inspector input, .editor-inspector textarea, #add-stage')
  target?.scrollIntoView({ block: 'nearest' }); target?.focus()
}
async function publish() {
  if (busy.value || !document.value || issues.value.length || !updateSummary.value.trim()) return
  busy.value = true; error.value = ''
  try {
    const ticket = request
    await publishRoadmap(String(route.params.id), document.value.expectedVersion, updateSummary.value.trim())
    if (ticket !== request || !document.value) return
    baseline.value = cleanDocument(document.value); preview.value = false
    busy.value = false
    await router.replace(auth.isAdmin ? '/admin/official-roadmaps' : { name: 'roadmap-detail', params: { id: route.params.id } })
  } catch (cause) { report(cause) }
  finally { busy.value = false }
}
function beforeUnload(event: BeforeUnloadEvent) { if (isDirty.value) { event.preventDefault(); event.returnValue = '' } }
function outsideContext(event: PointerEvent) {
  if (!(event.target as HTMLElement).closest('.editor-context-menu')) contextMenu.value = null
  if (!(event.target as HTMLElement).closest('.publication-check')) checkOpen.value = false
}
onBeforeRouteLeave(() => !busy.value && (!isDirty.value || window.confirm('还有未保存的修改，确定离开吗？')))
watch([() => route.params.id, () => auth.sessionVersion], () => {
  request++; document.value = null; baseline.value = ''; history.value = []
  checkOpen.value = resetConfirm.value = false; serverIssues.value = []; serverCheckedDocument.value = ''
  preview.value = false; updateSummary.value = ''; busy.value = false
  if (auth.authenticated) void load()
}, { immediate: true })
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); window.addEventListener('pointerdown', outsideContext) })
onBeforeUnmount(() => { request++; clearTimeout(historyTimer); window.removeEventListener('beforeunload', beforeUnload); window.removeEventListener('pointerdown', outsideContext) })
</script>

<template>
  <section class="editor-page">
    <p class="route-breadcrumb">
      <RouterLink :to="auth.isAdmin ? '/admin/official-roadmaps' : '/roadmaps'">路线仓库</RouterLink><span>/</span><RouterLink :to="auth.isAdmin ? '/admin/official-roadmaps' : { name: 'roadmap-detail', params: { id: route.params.id } }">{{ auth.isAdmin ? '官方路线' : '路线详情' }}</RouterLink><span>/</span>编辑
    </p>
    <header class="editor-heading">
      <div class="route-title-line">
        <h1>{{ document?.title || '路线编辑器' }}</h1><span
          v-if="document"
          class="route-badge draft"
        >编辑中</span>
      </div>
      <div class="route-actions">
        <span
          v-if="document"
          class="save-indicator"
        >{{ busy ? '正在处理…' : isDirty ? '未保存的修改' : '已保存' }}</span>
        <button
          type="button"
          class="outline-link"
          :disabled="busy || !document || conflict"
          @click="save"
        >
          保存工作稿
        </button>
        <button
          type="button"
          class="primary-button"
          :disabled="busy || !document || conflict"
          @click="previewPublication"
        >
          预览并发布
        </button>
        <div
          v-if="document && !loading"
          class="publication-check"
          @keydown.esc.stop.prevent="closeChecks"
        >
          <button
            id="publication-check-toggle"
            type="button"
            class="publication-check-toggle"
            :data-status="issues.length ? 'invalid' : 'valid'"
            :aria-label="'发布检查：' + (issues.length ? issues.length + '项待完善' : '已通过')"
            :title="issues.length ? '查看待完善的发布内容' : '发布检查通过'"
            :aria-expanded="checkOpen"
            aria-controls="publication-check-list"
            :disabled="busy"
            @click="checkOpen ? closeChecks() : openChecks()"
          >
            <svg
              v-if="issues.length"
              viewBox="0 0 24 24"
              aria-hidden="true"
            ><path d="M12 3 22 21H2Z" /><path d="M12 9v5m0 3v.1" /></svg>
            <svg
              v-else
              viewBox="0 0 24 24"
              aria-hidden="true"
            ><circle
              cx="12"
              cy="12"
              r="9"
            /><path d="m8 12 3 3 5-6" /></svg>
          </button>
          <section
            v-if="checkOpen"
            id="publication-check-list"
            class="publication-check-list"
            role="region"
            aria-label="发布检查"
            tabindex="-1"
          >
            <header>
              <div>
                <h2>发布检查</h2><p role="status">
                  {{ issues.length ? '还有 ' + issues.length + ' 项待完善' : '检查通过' }}
                </p>
              </div><button
                type="button"
                class="check-close"
                aria-label="关闭发布检查"
                @click="closeChecks"
              >
                ×
              </button>
            </header>
            <ol v-if="issues.length">
              <li
                v-for="(issue, index) in issues"
                :key="index"
              >
                <button
                  type="button"
                  @click="locate(issue)"
                >
                  <span>{{ issue.message }}</span><small>{{ issueContext(issue) }}</small>
                </button>
              </li>
            </ol>
            <p
              v-else
              class="check-passed"
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
              ><circle
                cx="12"
                cy="12"
                r="9"
              /><path d="m8 12 3 3 5-6" /></svg>可以预览并发布
            </p>
          </section>
        </div>
        <div
          v-if="error && document && !preview"
          role="alert"
          class="form-error"
        >
          {{ error }}<button
            v-if="conflict || !document"
            type="button"
            class="text-button"
            @click="load"
          >
            重新加载工作稿
          </button>
        </div>
      </div>
    </header>
    <p
      v-if="loading"
      class="loading-message"
      role="status"
    >
      正在加载工作稿…
    </p>
    <div
      v-if="error && !document"
      role="alert"
      class="form-error"
    >
      {{ error }}<button
        v-if="conflict || !document"
        type="button"
        class="text-button"
        @click="load"
      >
        重新加载工作稿
      </button>
    </div>
    <div
      v-if="document && !loading"
      class="editor-body"
      :class="{ 'inspector-collapsed': !inspectorOpen }"
      :aria-busy="busy"
    >
      <aside
        class="editor-palette"
        aria-label="组件与大纲"
      >
        <button
          type="button"
          class="basic-panel-button"
          @click="kind = 'basic'; contextMenu = null; inspectorOpen = true"
        >
          基本信息 →
        </button>
        <h2>添加组件</h2>
        <button
          id="add-stage"
          type="button"
          class="component-tile"
          draggable="true"
          :disabled="busy"
          @dragstart="dragComponent($event, 'stage')"
          @click="addStage()"
        >
          ＋ 阶段
        </button>
        <button
          id="add-node"
          type="button"
          class="component-tile"
          draggable="true"
          :disabled="busy"
          @dragstart="dragComponent($event, 'node')"
          @click="addNode()"
        >
          ＋ 节点
        </button>
        <h2>路线大纲</h2>
        <ul class="editor-outline">
          <li
            v-for="(s, i) in document.stages"
            :key="s.id"
          >
            <button
              type="button"
              :class="{ selected: selectedId === s.id }"
              @click="select('stage', s.id, s.id)"
            >
              {{ i + 1 }}. {{ s.title || '未命名阶段' }}
            </button><ul>
              <li
                v-for="(n, j) in s.nodes"
                :key="n.id"
              >
                <button
                  type="button"
                  :class="{ selected: selectedId === n.id }"
                  @click="select('node', n.id, s.id)"
                >
                  {{ j + 1 }}. {{ n.title || '未命名节点' }}
                </button>
              </li>
            </ul>
          </li>
        </ul>
      </aside>
      <RoadmapCanvas
        :stages="document.stages"
        :connections="document.connections"
        editable
        :disabled="busy"
        :selected-id="selectedId"
        :selected-kind="kind"
        @select="select"
        @move="move"
        @connect="connect"
        @context="showContext"
        @remove-connection="removeConnection"
        @add-stage="addStage"
        @add-node="addNode"
      />
      <aside
        class="editor-inspector"
        :class="{ collapsed: !inspectorOpen }"
        aria-label="组件设置"
      >
        <div class="inspector-heading">
          <span v-if="inspectorOpen">{{ kind === 'basic' ? '基本信息' : kind === 'stage' ? '阶段设置' : '节点设置' }}</span>
          <button
            type="button"
            :aria-label="inspectorOpen ? '收起设置区' : '展开设置区'"
            :title="inspectorOpen ? '收起设置区' : '展开设置区'"
            :aria-expanded="inspectorOpen"
            aria-controls="editor-component-settings"
            @click="inspectorOpen = !inspectorOpen"
          >
            {{ inspectorOpen ? '›' : '‹' }}
          </button>
        </div>
        <fieldset
          v-show="inspectorOpen"
          id="editor-component-settings"
          :disabled="busy"
        >
          <template v-if="kind === 'basic'">
            <div class="form-field">
              <label for="route-title">路线标题</label><input
                id="route-title"
                v-model="document.title"
                maxlength="120"
                required
              >
            </div>
            <div class="form-field">
              <label for="route-description">路线简介</label><textarea
                id="route-description"
                v-model="document.description"
                maxlength="1000"
                placeholder="建议说明路线内容、适合人群、所需基础和预期学习目标"
                rows="5"
              />
            </div>
            <div class="form-field">
              <label for="route-difficulty">难度</label><select
                id="route-difficulty"
                v-model="document.difficulty"
              >
                <option value="beginner">
                  入门
                </option><option value="intermediate">
                  进阶
                </option><option value="advanced">
                  高级
                </option>
              </select>
            </div>
            <div class="form-field">
              <label for="effort-note">参考投入时间</label>
              <input
                id="effort-note"
                v-model="document.effortNote"
                maxlength="200"
                placeholder="选填，如每周 3 小时，约 6 周"
              >
            </div>
          </template>
          <template v-else-if="stage && (kind === 'stage' || node)">
            <template v-if="kind === 'stage'">
              <div class="form-field">
                <label for="stage-title">阶段标题</label><input
                  id="stage-title"
                  v-model="stage.title"
                  maxlength="120"
                >
              </div>
              <div class="form-field">
                <label for="stage-description">阶段描述 </label><textarea
                  id="stage-description"
                  v-model="stage.description"
                  maxlength="10000"
                  rows="4"
                />
              </div>
              <div class="coordinate-fields">
                <div class="form-field">
                  <label for="stage-x">X 坐标</label><input
                    id="stage-x"
                    v-model.number="stage.canvasX"
                    type="number"
                    min="0"
                    max="9000"
                  >
                </div><div class="form-field">
                  <label for="stage-y">Y 坐标</label><input
                    id="stage-y"
                    v-model.number="stage.canvasY"
                    type="number"
                    min="0"
                    max="9000"
                  >
                </div>
              </div>
              <h3>阶段连线</h3>
              <div class="connection-selector">
                <select
                  aria-label="连线目标阶段"
                  :value="''"
                  @change="event => { connect(stage!.id, (event.target as HTMLSelectElement).value); (event.target as HTMLSelectElement).value = '' }"
                >
                  <option
                    disabled
                    value=""
                  >
                    选择目标阶段
                  </option><option
                    v-for="target in document.stages.filter(s => s.id !== stage!.id)"
                    :key="target.id"
                    :value="target.id"
                  >
                    {{ target.title || '未命名阶段' }}
                  </option>
                </select>
              </div>
              <div
                v-for="(edge, index) in document.connections"
                :key="edge.source + edge.target"
              >
                <div
                  v-if="edge.source === stage.id || edge.target === stage.id"
                  class="connection-row"
                >
                  <span>{{ document.stages.find(s => s.id === edge.source)?.title }} → {{ document.stages.find(s => s.id === edge.target)?.title }}</span><button
                    type="button"
                    aria-label="删除连线"
                    @click="removeConnection(index)"
                  >
                    ×
                  </button>
                </div>
              </div>
            </template>
            <template v-else-if="node">
              <div class="form-field">
                <label for="node-title">节点标题</label><input
                  id="node-title"
                  v-model="node.title"
                  maxlength="150"
                >
              </div>
              <div class="form-field">
                <label for="node-purpose">节点类型</label>
                <select
                  id="node-purpose"
                  :value="node.isOptional ? 'optional' : 'main'"
                  @change="node.isOptional = ($event.target as HTMLSelectElement).value === 'optional'; node.countsTowardProgress = !node.isOptional"
                >
                  <option value="main">
                    主线 · 计入进度
                  </option>
                  <option value="optional">
                    拓展 · 不计入进度
                  </option>
                </select>
              </div>
              <div
                v-if="node.stableKey"
                class="form-field"
              >
                <label for="node-change">学习要求变化</label>
                <select
                  id="node-change"
                  v-model="node.changePolicy"
                >
                  <option value="retain">
                    纠错或同目标调整 · 保留完成
                  </option>
                  <option value="reconfirm">
                    目标或任务变化 · 升级时重新确认
                  </option>
                </select>
              </div>
              <div class="form-field">
                <label for="node-content">节点内容描述</label><textarea
                  id="node-content"
                  v-model="node.content"
                  maxlength="10000"
                  rows="4"
                />
              </div>
              <div class="form-field">
                <label for="node-stage">所属阶段</label><select
                  id="node-stage"
                  :value="stage.id"
                  @change="changeNodeStage"
                >
                  <option
                    v-for="s in document.stages"
                    :key="s.id"
                    :value="s.id"
                  >
                    {{ s.title || '未命名阶段' }}
                  </option>
                </select>
              </div>
              <div class="reference-time">
                <label><input
                  type="checkbox"
                  :checked="node.estimatedMinutes !== null"
                  @change="referenceTime"
                >增加预计学习参考时间</label><input
                  v-if="node.estimatedMinutes !== null"
                  aria-label="预计学习分钟"
                  type="number"
                  min="1"
                  :value="node.estimatedMinutes"
                  @input="setMinutes"
                >
              </div>
              <h3>学习资源</h3>
              <div
                v-for="(resource, index) in node.resources"
                :key="resource.id"
                class="resource-editor"
              >
                <div class="resource-heading">
                  <span>资源 {{ index + 1 }}</span><button
                    type="button"
                    :aria-label="'删除资源' + (index + 1)"
                    @click="node.resources.splice(index, 1)"
                  >
                    删除
                  </button>
                </div>
                <div class="form-field">
                  <label :for="'resource-title-' + resource.id">资源名称</label><input
                    :id="'resource-title-' + resource.id"
                    v-model="resource.title"
                    maxlength="120"
                  >
                </div>
                <div class="form-field">
                  <label :for="'resource-type-' + resource.id">资源类型</label><select
                    :id="'resource-type-' + resource.id"
                    v-model="resource.resourceType"
                  >
                    <option value="article">
                      文章
                    </option><option value="video">
                      视频
                    </option><option value="book">
                      书籍
                    </option><option value="course">
                      课程
                    </option><option value="other">
                      其他
                    </option>
                  </select>
                </div>
                <div class="form-field">
                  <label :for="'resource-url-' + resource.id">资源链接</label><input
                    :id="'resource-url-' + resource.id"
                    v-model="resource.resourceUrl"
                    maxlength="2048"
                    placeholder="https://…"
                  >
                </div>
                <div class="resource-order">
                  <button
                    type="button"
                    :disabled="index === 0"
                    @click="node.resources.splice(index - 1, 0, node.resources.splice(index, 1)[0]!)"
                  >
                    上移
                  </button><button
                    type="button"
                    :disabled="index === node.resources.length - 1"
                    @click="node.resources.splice(index + 1, 0, node.resources.splice(index, 1)[0]!)"
                  >
                    下移
                  </button>
                </div>
              </div>
              <button
                id="add-node-resource"
                type="button"
                class="outline-link add-resource"
                :disabled="node.resources.length >= 30"
                @click="addResource"
              >
                ＋ 添加资源
              </button>
              <div class="form-field tips-field">
                <label for="node-tips">小贴士 </label><textarea
                  id="node-tips"
                  v-model="node.tips"
                  maxlength="10000"
                  rows="3"
                />
              </div>
            </template>
            <div class="component-actions">
              <button
                type="button"
                class="outline-link"
                :disabled="selectedIndex <= 0"
                @click="shift(-1)"
              >
                上移{{ kind === 'stage' ? '阶段' : '节点' }}
              </button><button
                type="button"
                class="outline-link"
                :disabled="selectedIndex < 0 || selectedIndex >= (orderedComponents?.length || 0) - 1"
                @click="shift(1)"
              >
                下移{{ kind === 'stage' ? '阶段' : '节点' }}
              </button><button
                type="button"
                class="text-button danger-text"
                @click="deleteConfirm = true"
              >
                删除{{ kind === 'stage' ? '阶段' : '节点' }}
              </button>
            </div>
          </template>
          <p
            v-else
            class="field-hint"
          >
            请从画布或大纲中选择一个组件。
          </p>
        </fieldset>
      </aside>
      <div class="editor-history">
        <button
          id="editor-undo"
          type="button"
          class="outline-link"
          :disabled="busy"
          @click="undo"
        >
          撤销
        </button><button
          type="button"
          class="outline-link"
          :disabled="busy || !document.stages.length && !document.connections.length"
          title="清空画布，重新开始"
          @click="resetConfirm = true"
        >
          重做
        </button><span>{{ document.stages.length }} 个阶段 · {{ nodeCount }} 个节点</span>
      </div>
    </div>
    <div
      v-if="contextMenu"
      class="editor-context-menu"
      role="menu"
      aria-label="组件操作"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @keydown="contextKeys"
    >
      <button
        type="button"
        role="menuitem"
        @click="contextAction('edit')"
      >
        编辑
      </button><button
        type="button"
        role="menuitem"
        @click="contextAction('delete')"
      >
        删除
      </button>
    </div>
    <AppDialog
      v-if="resetConfirm"
      title="清空画布"
      :busy="busy"
      @close="resetConfirm = false"
    >
      <p>清空全部阶段、节点、资源和连线，保留路线基本信息。保存前可通过“撤销”恢复；已发布版本不受影响。</p>
      <template #footer>
        <button
          type="button"
          class="outline-link"
          @click="resetConfirm = false"
        >
          取消
        </button>
        <button
          type="button"
          class="primary-button danger"
          @click="resetCanvas"
        >
          确认清空
        </button>
      </template>
    </AppDialog>
    <AppDialog
      v-if="deleteConfirm"
      title="确认删除组件"
      @close="deleteConfirm = false"
    >
      <p>{{ kind === 'stage' ? '删除阶段会同时移除其节点、资源及相关阶段连线。已发布版本不受影响。' : '删除节点会移除其内容与资源。已发布版本不受影响。' }}</p><template #footer>
        <button
          class="outline-link"
          type="button"
          @click="deleteConfirm = false"
        >
          取消
        </button><button
          class="primary-button danger"
          type="button"
          @click="deleteComponent"
        >
          确认删除
        </button>
      </template>
    </AppDialog>
    <AppDialog
      v-if="preview && document"
      title="工作稿预览与发布检查"
      :busy="busy"
      @close="preview = false"
    >
      <p
        v-if="error"
        role="alert"
        class="form-error"
      >
        {{ error }}
      </p>
      <h3>{{ document.title }}</h3><p class="preview-description">
        {{ document.description }}
      </p>
      <RoadmapCanvas
        :stages="document.stages"
        :connections="document.connections"
      />
      <h3>发布检查</h3>
      <ul
        v-if="issues.length"
        class="publication-issues"
      >
        <li
          v-for="(issue, index) in issues"
          :key="index"
        >
          <button
            type="button"
            @click="locate(issue)"
          >
            {{ issue.message }} · 定位修改 →
          </button>
        </li>
      </ul>
      <p
        v-else
        class="form-success"
        role="status"
      >
        检查通过 · V{{ nextVersion }}
      </p>
      <div class="form-field">
        <label for="update-summary">本次更新说明</label>
        <textarea
          id="update-summary"
          v-model="updateSummary"
          maxlength="2000"
          rows="3"
          placeholder="简述本次发布的内容或变化"
        />
      </div>
      <p v-if="document.effortNote">
        {{ document.effortNote }} · 仅供参考
      </p>
      <p
        v-if="error"
        class="form-error"
        role="alert"
      >
        {{ error }}
      </p>
      <template #footer>
        <button
          class="outline-link"
          type="button"
          :disabled="busy"
          @click="preview = false"
        >
          返回编辑
        </button><button
          class="primary-button"
          type="button"
          :disabled="busy || !!issues.length || !updateSummary.trim()"
          @click="publish"
        >
          {{ busy ? '正在发布…' : '发布到社区' }}
        </button>
      </template>
    </AppDialog>
  </section>
</template>

<style scoped>
.publication-check { position: relative; flex-shrink: 0; }
.publication-check-toggle { display: grid; place-items: center; width: 44px; height: 44px; border: 1px solid transparent; border-radius: 8px; background: transparent; cursor: pointer; }
.publication-check svg { width: 24px; height: 24px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
.publication-check-toggle[data-status=invalid] { color: var(--error, #a13e35); }
.publication-check-toggle[data-status=invalid] svg path:first-child { fill: var(--error-soft, #fff1ee); }
.publication-check-toggle[data-status=valid] { color: var(--green); }
.publication-check-toggle[data-status=valid] circle { fill: var(--green-soft); }
.publication-check-toggle:hover, .publication-check-toggle[aria-expanded=true] { background: var(--surface-soft, #f3f6f4); border-color: var(--line); }
.publication-check button:focus-visible, .publication-check-list:focus-visible { outline: 2px solid var(--green); outline-offset: 3px; }
.publication-check-list { position: absolute; right: 0; top: calc(100% + 10px); width: min(390px, calc(100vw - 40px)); max-height: min(65vh, 480px); overflow-y: auto; z-index: 30; background: var(--paper); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 12px 36px #173f2e1a; padding: 16px; color: var(--ink); }
.publication-check-list header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.publication-check-list h2 { margin: 0 0 5px; font-size: 16px; }
.publication-check-list header p { margin: 0; color: var(--muted); font-size: 13px; }
.check-close { width: 32px; min-height: 32px; border: none; border-radius: 5px; color: var(--muted); background: transparent; font-size: 23px; cursor: pointer; }
.publication-check-list ol { list-style: none; padding: 0; margin: 12px 0 0; }
.publication-check-list li + li { border-top: 1px solid var(--line); }
.publication-check-list li button { display: flex; flex-direction: column; gap: 5px; width: 100%; min-height: 52px; padding: 12px 8px; text-align: left; font: inherit; font-size: 13px; color: var(--ink); background: transparent; border: none; border-radius: 5px; cursor: pointer; overflow-wrap: anywhere; }
.publication-check-list li button:hover { background: var(--green-soft); }
.publication-check-list small { font-size: 12px; color: var(--muted); }
.check-passed { display: flex; align-items: center; gap: 9px; margin: 20px 0 8px; color: var(--green); font-size: 14px; }
@media (max-width: 760px) { .editor-heading { position: relative; } .publication-check { position: static; } .publication-check-list { top: 100%; right: 0; } }
</style>
