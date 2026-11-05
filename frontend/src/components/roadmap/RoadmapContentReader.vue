<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import type { Connection, DetailStage } from '../../types/roadmap'
import RoadmapCanvas from './RoadmapCanvas.vue'
import AppIcon from '../common/AppIcon.vue'

// 只负责内容导航；身份、版本来源及后续学习操作由外层页面提供。
const props = defineProps<{
  stages: DetailStage[]; connections: Connection[]; initialNodeId?: string; initialStageId?: string
  visitedResourceIds?: string[]; visitError?: string
  learning?: boolean; completedNodeIds?: string[]; title?: string
  progressCompleted?: number; progressTotal?: number
}>()
const emit = defineEmits<{ viewNode: [id: string]; visitResource: [id: string] }>()
const selectedKind = ref<'stage' | 'node'>('node')
const selectedId = ref('')
const selectedStageId = ref('')
const expanded = ref(new Set<string>())
const view = ref<'content' | 'graph'>('content')
const content = ref<HTMLElement>()
const tabsId = 'reader-' + useId()
const stage = computed(() => props.stages.find(item => item.id === selectedStageId.value))
const node = computed(() => stage.value?.nodes.find(item => item.id === selectedId.value))
const nodes = computed(() => props.stages.flatMap(stage => stage.nodes.map(node => ({ stage, node }))))
const index = computed(() => selectedKind.value === 'node' ? nodes.value.findIndex(item => item.node.id === selectedId.value) : -1)
const stageNumber = computed(() => props.stages.findIndex(item => item.id === selectedStageId.value) + 1)
const completedInStage = computed(() => stage.value?.nodes.filter(item => props.completedNodeIds?.includes(item.id)).length || 0)
const stageResources = computed(() => stage.value?.nodes.reduce((count, item) => count + (item.resources?.length || 0), 0) || 0)

function select(kind: 'stage' | 'node', id: string, stageId: string) {
  const target = props.stages.find(stage => stage.id === stageId)
  if (!target || (kind === 'node' && !target.nodes.some(node => node.id === id))) return
  selectedKind.value = kind; selectedId.value = id; selectedStageId.value = stageId
  expanded.value.add(stageId); view.value = 'content'
  if (kind === 'node') emit('viewNode', id)
  void nextTick(() => content.value?.scrollTo({ top: 0 }))
}
watch(() => [props.stages, props.initialNodeId, props.initialStageId], () => {
  expanded.value = new Set()
  const initial = nodes.value.find(item => item.node.id === props.initialNodeId)
  const initialStage = props.stages.find(stage => stage.id === props.initialStageId)
  const first = initial || nodes.value[0]
  if (initialStage && !initial) select('stage', initialStage.id, initialStage.id)
  else if (first) select('node', first.node.id, first.stage.id)
  else if (props.stages[0]) select('stage', props.stages[0].id, props.stages[0].id)
  else { selectedId.value = ''; selectedStageId.value = ''; view.value = 'content' }
}, { immediate: true })
function toggle(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}
function step(direction: number) {
  if (index.value < 0) return
  const target = nodes.value[index.value + direction]
  if (target) select('node', target.node.id, target.stage.id)
}
function openStageStart() {
  const current = stage.value
  const first = current?.nodes[0]
  if (current && first) select('node', first.id, current.id)
}
function tabKeys(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  const tabs = event.currentTarget as HTMLElement
  view.value = event.key === 'Home' ? 'content' : event.key === 'End' ? 'graph' : view.value === 'content' ? 'graph' : 'content'
  void nextTick(() => tabs.querySelector<HTMLButtonElement>('[aria-selected="true"]')?.focus())
  event.preventDefault()
}
function resourceLink(value: string) {
  try {
    const url = new URL(value)
    if (['http:', 'https:'].includes(url.protocol) && !url.username && !url.password) return url.href
  } catch { /* 旧内容中的无效链接只显示名称，不提供可执行入口。 */ }
  return undefined
}
function resourceType(value: string) {
  return ({ article: '文章', video: '视频', document: '文档', book: '书籍', course: '课程', other: '其他' })[value] || '资源'
}
</script>

<template>
  <div
    class="content-reader-layout"
    :class="{ 'with-actions': !!$slots.actions, 'learning-reader': learning }"
  >
    <nav
      class="content-reader-directory"
      aria-label="路线目录"
    >
      <p
        v-if="learning"
        class="directory-eyebrow"
      >
        学习过程 / 路线目录
      </p>
      <h2>{{ learning && title ? title : '路线目录' }}</h2>
      <p
        v-if="learning"
        class="directory-progress"
      >
        主线已完成 {{ progressCompleted ?? completedNodeIds?.length ?? 0 }} / {{ progressTotal ?? nodes.length }} 个节点
      </p>
      <ol class="reader-stages">
        <li
          v-for="(item, i) in stages"
          :key="item.id"
        >
          <div class="reader-stage-heading">
            <button
              type="button"
              :aria-label="'查看阶段：' + item.title"
              :class="{ selected: selectedKind === 'stage' && selectedId === item.id }"
              @click="select('stage', item.id, item.id)"
            >
              <span class="reader-stage-number">{{ String(i + 1).padStart(2, '0') }}</span>{{ item.title || '未命名阶段' }}
              <span
                v-if="learning"
                class="reader-stage-count"
              >{{ item.nodes.length }} 节</span>
            </button>
            <button
              type="button"
              :aria-label="(expanded.has(item.id) ? '折叠阶段：' : '展开阶段：') + item.title"
              :aria-expanded="expanded.has(item.id)"
              :aria-controls="tabsId + '-stage-' + item.id"
              @click="toggle(item.id)"
            >
              {{ expanded.has(item.id) ? '⌃' : '⌄' }}
            </button>
          </div>
          <ol
            v-show="expanded.has(item.id)"
            :id="tabsId + '-stage-' + item.id"
            class="reader-directory-nodes"
          >
            <li
              v-for="(child, j) in item.nodes"
              :key="child.id"
            >
              <button
                type="button"
                :aria-label="child.title || '未命名节点'"
                :aria-current="selectedKind === 'node' && selectedId === child.id ? 'true' : undefined"
                :class="{ selected: selectedKind === 'node' && selectedId === child.id }"
                @click="select('node', child.id, item.id)"
              >
                <span
                  v-if="learning"
                  class="reader-node-dot"
                  :class="{ complete: completedNodeIds?.includes(child.id) }"
                  :aria-label="completedNodeIds?.includes(child.id) ? '已完成' : '未完成'"
                >{{ completedNodeIds?.includes(child.id) ? '✓' : '' }}</span>
                <span>{{ learning ? `${i + 1}.${j + 1}` : `${j + 1}.` }}</span><span class="reader-node-title">{{ child.title || '未命名节点' }}</span>
                <small
                  v-if="learning && child.estimatedMinutes != null"
                  class="reader-node-minutes"
                >{{ child.estimatedMinutes }}分钟</small>
              </button>
            </li>
          </ol>
        </li>
      </ol>
      <p
        v-if="!stages.length"
        class="field-hint"
      >
        暂未添加阶段。
      </p>
    </nav>
    <section class="content-reader-main">
      <div
        class="reader-view-tabs"
        role="tablist"
        aria-label="内容视图"
        @keydown="tabKeys"
      >
        <button
          :id="tabsId + '-content-tab'"
          type="button"
          role="tab"
          :aria-selected="view === 'content'"
          :aria-controls="tabsId + '-content'"
          :tabindex="view === 'content' ? 0 : -1"
          @click="view = 'content'"
        >
          {{ selectedKind === 'stage' ? '阶段概览' : '节点内容' }}
        </button>
        <button
          :id="tabsId + '-graph-tab'"
          type="button"
          role="tab"
          :aria-selected="view === 'graph'"
          :aria-controls="tabsId + '-graph'"
          :tabindex="view === 'graph' ? 0 : -1"
          @click="view = 'graph'"
        >
          路线图
        </button>
      </div>
      <div
        v-if="view === 'content'"
        :id="tabsId + '-content'"
        class="reader-content-panel"
        role="tabpanel"
        :aria-labelledby="tabsId + '-content-tab'"
      >
        <section
          ref="content"
          class="reader-content-body"
          role="region"
          aria-label="路线内容只读浏览"
          tabindex="0"
        >
          <template v-if="selectedKind === 'stage' && stage">
            <header class="reader-stage-overview">
              <span class="reader-stage-kicker">阶段 {{ String(stageNumber).padStart(2, '0') }} / {{ stages.length }}</span>
              <h2>{{ stage.title || '未命名阶段' }}</h2>
              <div class="reader-stage-stats">
                <span><AppIcon name="list" />{{ stage.nodes.length }} 个学习节点</span><span><AppIcon name="repository" />{{ stageResources }} 份资源</span><span v-if="learning"><AppIcon name="check" />已完成 {{ completedInStage }} / {{ stage.nodes.length }}</span>
              </div>
            </header>
            <p class="readonly-text reader-stage-description">
              {{ stage.description || '暂未填写阶段描述' }}
            </p>
            <div class="reader-stage-section-heading">
              <h3>本阶段内容</h3><span>选择节点，查看内容与资源</span>
            </div>
            <ol class="reader-stage-nodes">
              <li
                v-for="(child, childIndex) in stage.nodes"
                :key="child.id"
              >
                <button
                  class="reader-stage-node"
                  :class="{ completed: learning && completedNodeIds?.includes(child.id) }"
                  type="button"
                  @click="select('node', child.id, stage.id)"
                >
                  <span class="reader-stage-node-index"><AppIcon
                    v-if="learning && completedNodeIds?.includes(child.id)"
                    name="check"
                  /><template v-else>{{ String(childIndex + 1).padStart(2, '0') }}</template></span>
                  <span class="reader-stage-node-copy"><strong>{{ child.title || '未命名节点' }}</strong><span>{{ child.resources?.length || 0 }} 份资源<span v-if="child.estimatedMinutes != null"> · 参考 {{ child.estimatedMinutes }} 分钟</span></span></span>
                  <span class="reader-stage-node-state">{{ learning && completedNodeIds?.includes(child.id) ? '已完成' : '查看内容' }}</span><span
                    class="reader-stage-node-arrow"
                    aria-hidden="true"
                  >›</span>
                </button>
              </li>
            </ol>
            <p
              v-if="!stage.nodes.length"
              class="reader-stage-empty"
            >
              此阶段暂未添加节点。
            </p>
          </template>
          <template v-else-if="node && stage">
            <h2>{{ node.title || '未命名节点' }}</h2>
            <div class="reader-node-meta">
              <span>{{ stage.title }} / 节点 {{ stage.nodes.findIndex(item => item.id === selectedId) + 1 }}</span><span
                v-if="node.estimatedMinutes != null"
                class="version-badge"
              >参考 {{ node.estimatedMinutes }} 分钟 · 仅供参考</span>
            </div>
            <h3>内容描述</h3>
            <p class="readonly-text">
              {{ node.content || '暂未填写节点内容' }}
            </p>
            <h3>学习资源</h3>
            <p v-if="learning && visitError" class="form-error" role="alert">{{ visitError }}</p>
            <ul
              v-if="node.resources?.length"
              class="reader-resource-cards"
            >
              <li
                v-for="resource in node.resources"
                :key="resource.id"
                :class="{ 'resource-visited': learning && visitedResourceIds?.includes(resource.id) }"
              >
                <span class="reader-resource-type">{{ resourceType(resource.resourceType) }}</span>
                <a
                  v-if="resourceLink(resource.resourceUrl)"
                  :href="resourceLink(resource.resourceUrl)"
                  :aria-label="resource.title || '未命名资源'"
                  target="_blank"
                  rel="noopener noreferrer"
                  @click="learning && emit('visitResource', resource.id)"
                  @auxclick="learning && $event.button === 1 && emit('visitResource', resource.id)"
                ><strong>{{ resource.title || '未命名资源' }}</strong><span aria-hidden="true">{{ learning && visitedResourceIds?.includes(resource.id) ? '再次打开 ↗' : '打开资源 ↗' }}</span></a>
                <span v-else>{{ resource.title || '未命名资源' }}（链接未填写或不可用）</span>
                <span v-if="learning && visitedResourceIds?.includes(resource.id)" class="resource-visited-badge" title="表示打开过链接，与节点完成独立">已访问</span>
              </li>
            </ul>
            <p
              v-else
              class="field-hint"
            >
              暂未添加学习资源。
            </p>
            <template v-if="node.tips">
              <h3>小贴士</h3><p class="reader-tip readonly-text">
                {{ node.tips }}
              </p>
            </template>
          </template>
          <p
            v-else
            class="reader-empty"
          >
            尚无可浏览内容，请先在编辑器中添加阶段与节点。
          </p>
        </section>
        <footer
          v-if="selectedKind === 'node'"
          class="reader-node-navigation"
          aria-label="节点浏览导航"
        >
          <button
            type="button"
            class="outline-link"
            :disabled="index <= 0"
            @click="step(-1)"
          >
            上一个节点
          </button>
          <span v-if="index >= 0">{{ index + 1 }} / {{ nodes.length }} 个节点</span>
          <button
            type="button"
            class="primary-button"
            :disabled="index < 0 || index >= nodes.length - 1"
            @click="step(1)"
          >
            下一个节点
          </button>
        </footer>
        <footer
          v-else-if="stage?.nodes.length"
          class="reader-node-navigation reader-stage-navigation"
        >
          <span>按目录顺序浏览，也可以自由选择想学的节点。</span>
          <button
            type="button"
            class="primary-button"
            @click="openStageStart"
          >
            查看首个节点 <span aria-hidden="true">›</span>
          </button>
        </footer>
      </div>
      <div
        v-else
        :id="tabsId + '-graph'"
        class="reader-graph-panel"
        role="tabpanel"
        :aria-labelledby="tabsId + '-graph-tab'"
      >
        <RoadmapCanvas
          :stages="stages"
          :connections="connections"
          selectable
          :selected-id="selectedId"
          :selected-kind="selectedKind"
          @select="select"
        />
        <p>拖动空白处浏览路线图，点击节点查看内容。</p>
      </div>
    </section>
    <aside
      v-if="$slots.actions"
      class="reader-actions"
    >
      <slot
        name="actions"
        :stage="stage"
        :node="node"
      />
    </aside>
  </div>
</template>
