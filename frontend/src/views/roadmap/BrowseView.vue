<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { roadmapDetail } from '../../api/roadmap'
import { useAuthStore } from '../../stores/auth'
import type { RoadmapDetail } from '../../types/roadmap'
import RoadmapContentReader from '../../components/roadmap/RoadmapContentReader.vue'

const route = useRoute()
const auth = useAuthStore()
const data = ref<RoadmapDetail | null>(null)
const loading = ref(true)
const error = ref('')
let request = 0
/** 沿用服务端权限；未通过检查前不挂载内容组件，不创建任何学习关系。 */
async function load() {
  const ticket = ++request
  loading.value = true; error.value = ''; data.value = null
  try {
    const result = await roadmapDetail(String(route.params.id), undefined, 'draft')
    if (ticket !== request) return
    if (!(result.canMaintain ?? result.isOwner)) throw new Error('仅作者或官方路线维护者可浏览。学习他人路线请从社区详情开始。')
    if (!result.canReadContent || result.status === 'disabled') throw new Error('该路线已被管理员下架，无法浏览完整内容。')
    data.value = result
  } catch (cause) {
    if (ticket === request) error.value = cause instanceof Error ? cause.message : '路线加载失败，请重试'
  } finally { if (ticket === request) loading.value = false }
}
watch([() => route.params.id, () => auth.user?.id, () => auth.sessionVersion], () => { void load() }, { immediate: true })
onBeforeUnmount(() => { request++ })
</script>

<template>
  <section class="roadmap-browse-page">
    <p class="route-breadcrumb">
      <RouterLink :to="auth.isAdmin ? '/admin/official-roadmaps' : '/roadmaps'">路线仓库</RouterLink><span>/</span><RouterLink :to="auth.isAdmin ? '/admin/official-roadmaps' : { name: 'roadmap-detail', params: { id: route.params.id } }">{{ auth.isAdmin ? '官方路线' : '路线详情' }}</RouterLink><span>/</span>浏览路线
    </p>
    <p
      v-if="loading"
      class="loading-message"
      role="status"
    >
      正在加载路线内容…
    </p>
    <div
      v-if="error"
      class="form-error"
      role="alert"
    >
      {{ error }}<button
        class="text-button"
        type="button"
        @click="load"
      >
        重新加载
      </button>
    </div>
    <header class="browse-route-heading">
      <div v-if="data">
        <div class="route-title-line">
          <h1>{{ data.title }}</h1><span
            class="route-badge"
            :class="data.status"
          >{{ data.contentSource === 'published' ? '已发布 V' + data.versionNo : '当前工作稿' }}</span>
        </div><p>作者 {{ data.author.nickname || data.author.username }} · {{ data.stageCount }} 个阶段 · {{ data.nodeCount }} 个节点</p>
      </div>
      <RouterLink
        class="outline-link"
        :to="auth.isAdmin ? '/admin/official-roadmaps' : { name: 'roadmap-detail', params: { id: route.params.id } }"
      >返回详情</RouterLink>
    </header>
    <template v-if="data">
      <RoadmapContentReader
        :stages="data.stages"
        :connections="data.connections"
        :initial-node-id="typeof route.query.node === 'string' ? route.query.node : undefined"
        :initial-stage-id="typeof route.query.stage === 'string' ? route.query.stage : undefined"
      />
    </template>
  </section>
</template>
