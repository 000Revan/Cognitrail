<script setup lang="ts">
import type { DetailNode } from '../../types/roadmap'
defineProps<{ node?: DetailNode; completed: boolean; writable: boolean; busy: boolean }>()
const emit = defineEmits<{ status: [id: string, completed: boolean] }>()
</script>

<template>
  <section class="learning-node-tools">
    <h2>节点进度</h2>
    <template v-if="node">
      <h3>{{ node.title }}</h3>
      <p class="field-hint">
        {{ node.countsTowardProgress === false ? '此节点不计入主线进度。' : '学完后可标记完成，也可撤销。' }}
      </p>
      <button
        type="button"
        class="outline-link"
        :disabled="busy || !writable"
        :aria-pressed="completed"
        @click="emit('status', node.id, !completed)"
      >
        {{ busy ? '保存中…' : completed ? '撤销完成' : '完成此节点' }}
      </button>
    </template>
    <p v-else>
      请选择一个节点。
    </p>
  </section>
</template>
