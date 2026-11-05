<script setup lang="ts">
import { computed, ref } from 'vue'
import { changeRoadmap } from '../../api/roadmap'
import type { RoadmapSummary } from '../../types/roadmap'
import AppDialog from '../common/AppDialog.vue'

const props = defineProps<{ route: RoadmapSummary; action: 'delete' | 'archive' | 'restore' | 'withdraw' }>()
const emit = defineEmits<{ close: []; done: [] }>()
const busy = ref(false)
const error = ref('')
const title = computed(() => ({
  delete: '永久删除草稿', archive: '归档路线',
  restore: '恢复到仓库', withdraw: '撤回路线',
})[props.action])
const description = computed(() => ({
  delete: '删除后将永久移除这份从未发布的草稿及其阶段、节点、资源和连线，无法恢复。',
  archive: '归档后停止公开分发。已有发布版本、学习及收藏关系保留。',
  restore: '恢复到仓库，并恢复原公开版的分发。平台下架限制继续有效。',
  withdraw: '路线将从社区隐藏，随后可编辑工作稿。已有学习者使用的发布版本和历史记录不会改变。',
})[props.action])
async function submit() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await changeRoadmap(props.route.id, props.route.editVersion, props.action); emit('done') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '操作失败，请重试' }
  finally { busy.value = false }
}
</script>

<template>
  <AppDialog
    :title="title"
    :busy="busy"
    @close="emit('close')"
  >
    <p class="dialog-route-title">
      {{ route.title }}
    </p><p>{{ description }}</p>
    <p
      v-if="error"
      class="form-error"
      role="alert"
    >
      {{ error }}
    </p>
    <template #footer>
      <button
        type="button"
        class="outline-link"
        :disabled="busy"
        @click="emit('close')"
      >
        取消
      </button>
      <button
        type="button"
        class="primary-button"
        :class="{ danger: action === 'delete' }"
        :disabled="busy"
        @click="submit"
      >
        {{ busy ? '正在处理…' : '确认' + title }}
      </button>
    </template>
  </AppDialog>
</template>
