<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { myEnrollments } from '../../api/enrollment'
import { useAuthStore } from '../../stores/auth'
import type { EnrollmentSummary } from '../../types/enrollment'
import { formatDate } from '../../domain/roadmap'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const abandoned = computed(() => route.query.status === 'abandoned')
const page = computed(() => Math.max(1, Number(route.query.page) || 1))
const items = ref<EnrollmentSummary[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const pages = computed(() => Math.max(1, Math.ceil(total.value / 12)))
let generation = 0
async function load() {
  const ticket = ++generation
  items.value = []; total.value = 0; loading.value = true; error.value = ''
  if (!auth.authenticated) { loading.value = false; return }
  try {
    const result = await myEnrollments({ status: abandoned.value ? 'abandoned' : 'active', page: page.value })
    if (ticket !== generation) return
    items.value = result.items; total.value = result.total
    if (page.value > pages.value) await router.replace({ query: { ...route.query, page: pages.value > 1 ? String(pages.value) : undefined } })
  } catch (cause) { if (ticket === generation) error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { if (ticket === generation) loading.value = false }
}
watch([() => route.fullPath, () => auth.user?.id, () => auth.sessionVersion], () => { void load() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++ })
</script>
<template>
  <section class="content-page learning-list-page">
    <header class="discovery-heading">
      <div>
        <p class="eyebrow">
          YOUR LEARNING
        </p><h1>我的学习</h1><p>每条路线保留一份学习关系，继续上次的位置。</p>
      </div><RouterLink
        to="/dashboard"
        class="outline-link"
      >打卡日历</RouterLink>
    </header>
    <div
      class="route-tabs"
      aria-label="学习状态筛选"
    >
      <button
        type="button"
        :class="{ active: !abandoned }"
        :aria-pressed="!abandoned"
        @click="router.push('/learning')"
      >
        学习中
      </button>
      <button
        type="button"
        :class="{ active: abandoned }"
        :aria-pressed="abandoned"
        @click="router.push('/learning?status=abandoned')"
      >
        已退出的历史
      </button>
    </div>
    <p
      v-if="loading"
      role="status"
    >
      正在加载学习路线…
    </p>
    <p
      v-else-if="error"
      role="alert"
      class="form-error"
    >
      {{ error }} <button
        type="button"
        class="text-button"
        @click="load"
      >
        重新加载
      </button>
    </p>
    <div
      v-else-if="!items.length"
      class="feature-placeholder"
    >
      <h2>{{ abandoned ? '暂无已退出的学习历史' : '暂无学习中的路线' }}</h2><RouterLink
        to="/"
        class="outline-link"
      >去社区发现</RouterLink>
    </div>
    <div
      v-else
      class="learning-card-list"
    >
      <article
        v-for="item in items"
        :key="item.id"
        class="learning-card"
      >
        <div class="route-title-line">
          <h2>
            <RouterLink
              :to="{ name: 'roadmap-detail', params: { id: item.roadmapId } }"
              class="learning-roadmap-link"
            >{{ item.title }}</RouterLink>
          </h2><span class="version-badge">学习版 V{{ item.versionNo }}</span>
        </div>
        <p v-if="item.description">
          {{ item.description }}
        </p>
        <p
          v-if="!item.contentAvailable"
          class="form-error"
        >
          内容已下架，正文与新增学习操作不可用。
        </p>
        <p
          v-if="item.hasNewVersion"
          class="route-info"
        >
          <span
            v-if="item.updatePromptDismissed"
            class="version-badge"
          >新版 V{{ item.currentVersionNo }}</span>
          <span v-else>已有新版 V{{ item.currentVersionNo }}，当前保留 V{{ item.versionNo }}。</span>
        </p>
        <p class="route-counts">
          主线已完成 {{ item.completedNodeCount }} / {{ item.progressNodeCount }} · {{ item.progressPercent }}% · 加入于 {{ formatDate(item.startedAt) }}
        </p>
        <footer class="route-actions">
          <RouterLink
            :to="{ name: 'learning-content', params: { id: item.id } }"
            class="primary-button"
          >{{ item.status === 'abandoned' ? '查看与恢复原版' : '继续学习' }}</RouterLink>
          <RouterLink
            :to="{ name: 'learning-history', params: { id: item.id } }"
            class="outline-link"
          >打卡记录</RouterLink>
        </footer>
      </article>
    </div>
    <footer
      v-if="!loading && !error && total"
      class="route-pagination"
    >
      <span>共 {{ total }} 条路线</span>
      <button
        type="button"
        class="outline-link"
        :disabled="page <= 1"
        @click="router.push({ query: { ...route.query, page: String(page - 1) } })"
      >
        上一页
      </button><span>{{ page }} / {{ pages }}</span>
      <button
        type="button"
        class="outline-link"
        :disabled="page >= pages"
        @click="router.push({ query: { ...route.query, page: String(page + 1) } })"
      >
        下一页
      </button>
    </footer>
  </section>
</template>

<style scoped>
.learning-roadmap-link:hover { color: var(--green); text-decoration: underline; text-underline-offset: 4px; }
.learning-roadmap-link:focus-visible { outline: 2px solid var(--green); outline-offset: 4px; border-radius: 3px; }
</style>
