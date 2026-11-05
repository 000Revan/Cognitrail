<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import type { Connection, GraphStage } from '../../types/roadmap'
import { stageSize } from '../../domain/roadmap'

const props = defineProps<{
  stages: GraphStage[]; connections: Connection[]; editable?: boolean
  selectedId?: string; selectedKind?: string; disabled?: boolean
  selectable?: boolean
}>()
const emit = defineEmits<{
  select: [kind: 'stage' | 'node', id: string, stageId: string]
  move: [kind: 'stage' | 'node', id: string, x: number, y: number]
  connect: [source: string, target: string]
  removeConnection: [index: number]
  context: [kind: 'stage' | 'node', id: string, stageId: string, x: number, y: number]
  addStage: [x: number, y: number]
  addNode: [stageId: string, x: number, y: number]
}>()
const viewport = ref<HTMLElement>()
const world = ref<HTMLElement>()
const markerId = 'stage-arrow-' + useId()
const zoom = ref(0.8)
const connectionSource = ref<string | null>(null)
const pointer = ref({ x: 0, y: 0 })
const panning = ref(false)
let pan: { pointerId: number; clientX: number; clientY: number; left: number; top: number } | null = null
let drag: { kind: 'stage' | 'node'; id: string; x: number; y: number; clientX: number; clientY: number } | null = null
const sizes = computed(() => Object.fromEntries(props.stages.map(s => [s.id, stageSize(s)])))
const width = computed(() => Math.max(1400, ...props.stages.map(s => s.canvasX + sizes.value[s.id]!.width + 120)))
const height = computed(() => Math.max(1000, ...props.stages.map(s => s.canvasY + sizes.value[s.id]!.height + 120)))
const canEdit = computed(() => props.editable && !props.disabled)
const edgePaths = computed(() => props.connections.map(edge => {
  const source = props.stages.find(s => s.id === edge.source)
  const target = props.stages.find(s => s.id === edge.target)
  return source && target ? curve(
    source.canvasX + sizes.value[source.id]!.width, source.canvasY + sizes.value[source.id]!.height / 2,
    target.canvasX, target.canvasY + sizes.value[target.id]!.height / 2,
  ) : ''
}))
const pendingPath = computed(() => {
  const source = props.stages.find(s => s.id === connectionSource.value)
  return source ? curve(source.canvasX + sizes.value[source.id]!.width,
    source.canvasY + sizes.value[source.id]!.height / 2, pointer.value.x, pointer.value.y) : ''
})
function curve(x: number, y: number, targetX: number, targetY: number) {
  const bend = Math.max(70, Math.abs(targetX - x) / 2)
  return 'M ' + x + ' ' + y + ' C ' + (x + bend) + ' ' + y + ', ' + (targetX - bend) + ' ' + targetY + ', ' + targetX + ' ' + targetY
}
function point(event: PointerEvent | DragEvent) {
  const bounds = world.value!.getBoundingClientRect()
  return { x: Math.max(0, (event.clientX - bounds.left) / zoom.value),
    y: Math.max(0, (event.clientY - bounds.top) / zoom.value) }
}
function beginDrag(event: PointerEvent, kind: 'stage' | 'node', id: string, stageId: string, x: number, y: number) {
  if (!canEdit.value || event.button !== 0) return
  emit('select', kind, id, stageId)
  if (connectionSource.value) return
  event.preventDefault()
  drag = { kind, id, x, y, clientX: event.clientX, clientY: event.clientY }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}
/** 仅背景启动视野拖动，组件、连接点和连线继续使用各自的操作。 */
function beginPan(event: PointerEvent) {
  if (event.button !== 0 || !event.isPrimary || !viewport.value || drag || connectionSource.value) return
  if ((event.target as Element).closest('.stage-drag-heading, .graph-node, .stage-port, .edge-hit-area, button, a')) return
  const element = viewport.value
  const bounds = element.getBoundingClientRect()
  // 保留滚动条原生操作；滚动条不属于可拖动的画布背景。
  if (event.clientX >= bounds.left + element.clientWidth || event.clientY >= bounds.top + element.clientHeight) return
  event.preventDefault()
  pan = { pointerId: event.pointerId, clientX: event.clientX, clientY: event.clientY, left: element.scrollLeft, top: element.scrollTop }
  panning.value = true
  element.setPointerCapture(event.pointerId)
}
function pointerMove(event: PointerEvent) {
  if (pan && viewport.value && event.pointerId === pan.pointerId) {
    viewport.value.scrollLeft = pan.left - (event.clientX - pan.clientX)
    viewport.value.scrollTop = pan.top - (event.clientY - pan.clientY)
    return
  }
  if (connectionSource.value && world.value) pointer.value = point(event)
  if (!drag || !canEdit.value) return
  emit('move', drag.kind, drag.id,
    Math.min(9000, Math.max(0, Math.round(drag.x + (event.clientX - drag.clientX) / zoom.value))),
    Math.min(9000, Math.max(0, Math.round(drag.y + (event.clientY - drag.clientY) / zoom.value))))
}
function pointerUp(event: PointerEvent) {
  if (pan) {
    if (event.pointerId === pan.pointerId) stopPan()
    return
  }
  drag = null
  if (!connectionSource.value || !world.value) return
  const p = point(event)
  const target = props.stages.find(stage => {
    const size = sizes.value[stage.id]!
    return p.x >= stage.canvasX - 16 && p.x <= stage.canvasX + size.width + 16 &&
      p.y >= stage.canvasY - 16 && p.y <= stage.canvasY + size.height + 16 &&
      stage.id !== connectionSource.value
  })
  if (target) finishConnection(target.id)
}
function startConnection(event: PointerEvent, stage: GraphStage) {
  if (!canEdit.value || event.button !== 0) return
  event.preventDefault()
  connectionSource.value = stage.id
  pointer.value = point(event)
}
function finishConnection(target: string) {
  if (!canEdit.value || !connectionSource.value || target === connectionSource.value) return
  emit('connect', connectionSource.value, target)
  connectionSource.value = null
}
function context(event: MouseEvent, kind: 'stage' | 'node', id: string, stageId: string) {
  if (!canEdit.value) return
  event.preventDefault()
  emit('context', kind, id, stageId, event.clientX, event.clientY)
}
function drop(event: DragEvent, stage?: GraphStage) {
  if (!canEdit.value) return
  const kind = event.dataTransfer?.getData('application/x-cognitrail-component')
  if (!kind) return
  event.preventDefault(); event.stopPropagation()
  const p = point(event)
  if (kind === 'stage') emit('addStage', Math.min(9000, p.x), Math.min(9000, p.y))
  else if (kind === 'node' && stage) emit('addNode', stage.id,
    Math.min(8000, Math.max(8, p.x - stage.canvasX)),
    Math.min(8000, Math.max(64, p.y - stage.canvasY)))
}
function fit() {
  if (!viewport.value) return
  const right = Math.max(500, ...props.stages.map(s => s.canvasX + sizes.value[s.id]!.width + 50))
  const bottom = Math.max(340, ...props.stages.map(s => s.canvasY + sizes.value[s.id]!.height + 50))
  zoom.value = Math.min(1, Math.max(0.15, Math.min(viewport.value.clientWidth / right, viewport.value.clientHeight / bottom)))
  viewport.value.scrollTo({ left: 0, top: 0 })
}
function stopPan() {
  const pointerId = pan?.pointerId
  pan = null; panning.value = false
  if (pointerId !== undefined && viewport.value?.hasPointerCapture(pointerId)) viewport.value.releasePointerCapture(pointerId)
}
function cancelPointer() { stopPan(); drag = null; connectionSource.value = null }
function cancel(event: KeyboardEvent) { if (event.key === 'Escape') cancelPointer() }
let fitted = false
watch(() => props.stages.length, async length => {
  if (length && !fitted) { fitted = true; await nextTick(); fit() }
})
onMounted(async () => {
  window.addEventListener('pointermove', pointerMove)
  window.addEventListener('pointerup', pointerUp)
  window.addEventListener('pointercancel', cancelPointer)
  window.addEventListener('blur', cancelPointer)
  window.addEventListener('keydown', cancel)
  await nextTick()
  if (props.stages.length) { fitted = true; fit() }
})
onBeforeUnmount(() => {
  cancelPointer()
  window.removeEventListener('pointermove', pointerMove)
  window.removeEventListener('pointerup', pointerUp)
  window.removeEventListener('pointercancel', cancelPointer)
  window.removeEventListener('blur', cancelPointer)
  window.removeEventListener('keydown', cancel)
})
defineExpose({ fit })
</script>

<template>
  <div
    class="roadmap-canvas"
    :class="{ 'canvas-editable': editable, 'canvas-selectable': selectable }"
  >
    <div
      class="canvas-toolbar"
      aria-label="画布工具"
    >
      <button
        type="button"
        aria-label="缩小画布"
        @click="zoom = Math.max(.15, zoom - .1)"
      >
        −
      </button>
      <span>{{ Math.round(zoom * 100) }}%</span>
      <button
        type="button"
        aria-label="放大画布"
        @click="zoom = Math.min(1.5, zoom + .1)"
      >
        ＋
      </button>
      <button
        type="button"
        @click="fit"
      >
        适应画布
      </button>
      <span
        v-if="connectionSource"
        class="connection-help"
      >拖到或点击目标阶段的连接点；Escape取消</span>
    </div>
    <div
      ref="viewport"
      class="canvas-viewport"
      :class="{ 'is-panning': panning }"
      role="region"
      tabindex="0"
      aria-label="路线画布，可在空白处按住左键拖动视野"
      @pointerdown="beginPan"
      @lostpointercapture="stopPan"
      @dragover.prevent
      @drop="drop($event)"
    >
      <div
        class="canvas-scaled-space"
        :style="{ width: width * zoom + 'px', height: height * zoom + 'px' }"
      >
        <div
          ref="world"
          class="canvas-world"
          :style="{ width: width + 'px', height: height + 'px', transform: 'scale(' + zoom + ')' }"
        >
          <svg
            class="canvas-edges"
            :width="width"
            :height="height"
            aria-label="阶段连线"
          >
            <defs><marker
              :id="markerId"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            ><path
              d="M0 0L10 5L0 10Z"
              fill="#538572"
            /></marker></defs>
            <g
              v-for="(edge, index) in connections"
              :key="edge.source + '-' + edge.target"
            >
              <path
                :d="edgePaths[index]"
                stroke="#538572"
                stroke-width="2"
                fill="none"
                :marker-end="'url(#' + markerId + ')'"
              />
              <path
                v-if="canEdit"
                class="edge-hit-area"
                :d="edgePaths[index]"
                stroke="transparent"
                stroke-width="16"
                fill="none"
                role="button"
                tabindex="0"
                :aria-label="'删除第' + (index + 1) + '条连线'"
                @click="emit('removeConnection', index)"
                @keydown.enter="emit('removeConnection', index)"
              />
            </g>
            <path
              v-if="connectionSource"
              :d="pendingPath"
              stroke="#23785d"
              stroke-width="2"
              stroke-dasharray="6 5"
              fill="none"
            />
          </svg>
          <section
            v-for="(stage, i) in stages"
            :key="stage.id"
            class="graph-stage"
            :class="{ selected: selectedKind === 'stage' && selectedId === stage.id }"
            :data-stage-id="stage.id"
            :style="{ left: stage.canvasX + 'px', top: stage.canvasY + 'px', width: sizes[stage.id]!.width + 'px', height: sizes[stage.id]!.height + 'px' }"
            @drop="drop($event, stage)"
            @contextmenu.stop="context($event, 'stage', stage.id, stage.id)"
          >
            <div
              class="stage-drag-heading"
              :class="{ draggable: canEdit }"
              @pointerdown.stop="beginDrag($event, 'stage', stage.id, stage.id, stage.canvasX, stage.canvasY)"
            >
              <span class="stage-number">{{ String(i + 1).padStart(2, '0') }}</span>
              <button
                v-if="canEdit || selectable"
                type="button"
                :aria-label="'选择阶段：' + (stage.title || '未命名')"
                @click.stop="emit('select', 'stage', stage.id, stage.id)"
              >
                {{ stage.title || '未命名阶段' }}
              </button>
              <strong v-else>{{ stage.title || '未命名阶段' }}</strong>
              <span
                v-if="canEdit"
                class="drag-dots"
                aria-hidden="true"
              >⠿</span>
            </div>
            <button
              v-if="canEdit"
              type="button"
              class="stage-port input-port"
              :aria-label="'连接到阶段：' + stage.title"
              @pointerup.stop="finishConnection(stage.id)"
              @click.stop="finishConnection(stage.id)"
            />
            <button
              v-if="canEdit"
              type="button"
              class="stage-port output-port"
              :aria-label="'从阶段连线：' + stage.title"
              @pointerdown.stop="startConnection($event, stage)"
              @keydown.enter.prevent="connectionSource = stage.id"
            />
            <div
              v-for="(node, j) in stage.nodes"
              :key="node.id"
              class="graph-node"
              :class="{ selected: selectedKind === 'node' && selectedId === node.id }"
              :data-node-id="node.id"
              :style="{ left: node.canvasX + 'px', top: node.canvasY + 'px' }"
              @pointerdown.stop="beginDrag($event, 'node', node.id, stage.id, node.canvasX, node.canvasY)"
              @contextmenu.stop="context($event, 'node', node.id, stage.id)"
            >
              <span class="node-number">{{ j + 1 }}</span>
              <button
                v-if="canEdit || selectable"
                type="button"
                :aria-label="'选择节点：' + (node.title || '未命名')"
                @click.stop="emit('select', 'node', node.id, stage.id)"
              >
                {{ node.title || '未命名节点' }}
              </button>
              <span v-else>{{ node.title || '未命名节点' }}</span>
            </div>
          </section>
          <p
            v-if="!stages.length"
            class="canvas-empty"
          >
            {{ editable ? '从左侧添加阶段，再添加学习节点。' : '这条路线还没有阶段。' }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
