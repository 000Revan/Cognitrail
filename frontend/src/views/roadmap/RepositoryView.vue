<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminRoadmaps, createRoadmap, myRoadmaps } from '../../api/roadmap'
import { useAuthStore } from '../../stores/auth'
import type { RoadmapSummary } from '../../types/roadmap'
import { formatDate } from '../../domain/roadmap'
import AppIcon from '../../components/common/AppIcon.vue'
import AppDialog from '../../components/common/AppDialog.vue'
import RoadmapActionDialog from '../../components/roadmap/RoadmapActionDialog.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const management = computed(() => route.name === 'admin-official-roadmaps')
const official = computed(() => management.value)
const tabs = computed(() => management.value
  ? [{ value: '', label: '全部' }, { value: 'draft', label: '草稿' }, { value: 'published', label: '已发布' }, { value: 'disabled', label: '已下架' }]
  : [{ value: '', label: '全部' }, { value: 'draft', label: '草稿' }, { value: 'published', label: '已发布' }, { value: 'disabled', label: '管理员下架' }])
const archived = computed(() => route.query.archived === '1')
const state = ref('')
const query = ref('')
const page = ref(1)
const total = ref(0)
const items = ref<RoadmapSummary[]>([])
const loading = ref(false)
const error = ref('')
const creating = ref(false)
const newTitle = ref('')
const busy = ref(false)
const createError = ref('')
const selected = ref<{ route: RoadmapSummary; action: 'archive' | 'delete' | 'restore' | 'withdraw' } | null>(null)
const disabledRoute = ref<RoadmapSummary | null>(null)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / 12)))
let request = 0
async function load() {
  const ticket = ++request
  loading.value = true; error.value = ''
  try {
    const data = management.value
      ? await adminRoadmaps({ officialOnly: official.value, archived: archived.value, status: state.value || undefined, keyword: query.value, page: page.value })
      : await myRoadmaps({ archived: archived.value, state: state.value || undefined, q: query.value, page: page.value })
    if (ticket !== request) return
    items.value = data.items; total.value = data.total
    if (!data.items.length && page.value > 1) { page.value--; void load() }
  } catch (cause) { if (ticket === request) error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { if (ticket === request) loading.value = false }
}
watch([() => route.fullPath, () => auth.user?.id, () => auth.isAdmin, () => auth.sessionVersion], () => {
  page.value = 1; state.value = ''; items.value = []; total.value = 0
  selected.value = null; disabledRoute.value = null; creating.value = false; void load()
}, { immediate: true })
onBeforeUnmount(() => { request++ })
function filter(value: string) { state.value = value; page.value = 1; void load() }
function search() { page.value = 1; void load() }
async function create() {
  if (busy.value) return
  busy.value = true; createError.value = ''
  const ticket = request
  try {
    const created = await createRoadmap(newTitle.value.trim() || '未命名路线', official.value)
    if (ticket !== request) return
    creating.value = false
    await router.push({ name: 'roadmap-editor', params: { id: created.id } })
  } catch (cause) { createError.value = cause instanceof Error ? cause.message : '创建失败' }
  finally { busy.value = false }
}
async function completed() {
  selected.value = null
  document.querySelectorAll<HTMLDetailsElement>('.route-more').forEach(menu => { menu.open = false })
  await load()
}
</script>

<template>
  <section class="repository-page content-page route-library-layout">
    <header class="repository-heading">
      <div>
        <h1>{{ management ? official ? '官方路线管理' : '内容管理' : archived ? '已归档路线' : '我的创作' }}</h1>
      </div>
      <div class="route-actions">
        <RouterLink
          v-if="!management || official"
          class="outline-link"
          :to="official ? archived ? '/admin/official-roadmaps' : '/admin/official-roadmaps?archived=1' : archived ? '/roadmaps' : '/roadmaps?archived=1'"
        >{{ archived ? '返回路线仓库' : '已归档' }}</RouterLink>
        <button
          v-if="!archived && (!management || official)"
          type="button"
          class="primary-button"
          @click="creating = true; newTitle = ''; createError = ''"
        >
          ＋ {{ official ? '新建官方路线' : '创建路线' }}
        </button>
      </div>
    </header>
    <div class="repository-filters">
      <div
        class="route-tabs"
        aria-label="路线状态筛选"
      >
        <button
          v-for="tab in tabs"
          :key="tab.value"
          type="button"
          :class="{ active: state === tab.value }"
          :aria-pressed="state === tab.value"
          @click="filter(tab.value)"
        >
          {{ tab.label }}
        </button>
      </div>
      <form
        class="route-search"
        @submit.prevent="search"
      >
        <input
          v-model="query"
          aria-label="搜索路线标题"
          maxlength="120"
          placeholder="搜索路线标题"
        ><button
          type="submit"
          aria-label="搜索"
        >
          搜索
        </button>
      </form>
    </div>
    <p
      v-if="loading"
      role="status"
      class="loading-message"
    >
      正在加载路线…
    </p>
    <div
      v-if="error"
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
    </div>
    <div
      v-if="!loading && !error && !items.length"
      class="feature-placeholder"
    >
      <AppIcon name="repository" /><h2>{{ archived ? '还没有归档路线' : '还没有符合条件的路线' }}</h2>
      <p>{{ archived ? '曾发布的路线移出仓库后会保留在这里。' : '试试调整筛选，或者创建你的第一条路线。' }}</p>
    </div>
    <div
      class="route-list"
      :aria-busy="loading"
    >
      <article
        v-for="item in items"
        :key="item.id"
        class="repository-card"
      >
        <RouterLink
          class="route-card-main"
          :to="{ name: official ? 'roadmap-browse' : 'roadmap-detail', params: { id: item.id } }"
        >
          <span class="route-cover"><img
            v-if="item.coverUrl"
            :src="item.coverUrl"
            alt=""
            referrerpolicy="no-referrer"
            @error="($event.target as HTMLImageElement).style.display = 'none'"
          ><AppIcon
            v-else
            name="repository"
          /></span>
          <div class="route-card-copy">
            <div class="route-title-line"><h2>{{ item.title }}</h2><span
              class="route-badge"
              :class="item.status"
            >{{ item.status === 'draft' ? '草稿' : item.status === 'withdrawn' ? '作者撤回' : item.displayStatus }}</span></div>
            <p v-if="item.description">{{ item.description }}</p>
            <p v-if="item.versionNo">公开版 V{{ item.versionNo }}<template v-if="item.hasUnpublishedChanges"> · 工作稿待发布</template></p>
            <div class="library-card-stats"><span><AppIcon name="list" />{{ item.stageCount }} 个阶段 · {{ item.nodeCount }} 个节点</span><span v-if="item.learnerCount != null"><AppIcon name="user" />{{ item.learnerCount }} 人学习</span><span v-if="item.favoriteCount != null"><AppIcon name="bookmark" />{{ item.favoriteCount }} 人收藏</span><span v-if="management">{{ item.roadmapType === 'official' ? '官方路线' : '用户路线' }} · {{ item.author.nickname || item.author.username }}</span></div>
          </div>
        </RouterLink>
        <div class="route-card-meta">
          <time :datetime="item.updatedAt">更新于 {{ formatDate(item.updatedAt) }}</time>
          <div class="library-card-actions">
            <RouterLink
              v-if="management && !official"
              class="outline-link library-detail-link"
              :to="{ name: 'admin-roadmap-detail', params: { id: item.id }, query: { preview: 'draft' } }"
            >审查发布内容</RouterLink>
            <template v-else-if="!archived && item.status !== 'disabled'">
              <RouterLink
                v-if="item.status === 'draft' || item.status === 'published'"
                :class="item.status === 'draft' ? 'primary-button' : 'outline-link library-detail-link'"
                :to="{ name: 'roadmap-editor', params: { id: item.id } }"
              >{{ item.status === 'draft' ? '继续编辑' : '编辑工作稿' }}</RouterLink>
              <RouterLink
                class="outline-link library-detail-link"
                :to="{ name: 'roadmap-browse', params: { id: item.id } }"
              >预览工作稿</RouterLink>
            </template>
            <button
              v-else-if="item.status === 'disabled'"
              type="button"
              class="outline-link"
              @click="disabledRoute = item"
            >
              查看原因
            </button>
            <RouterLink
              v-else
              class="outline-link"
              :to="{ name: 'roadmap-detail', params: { id: item.id } }"
            >查看详情</RouterLink>
          </div>
        </div>
        <details
          v-if="!management || official"
          class="route-more"
        >
          <summary :aria-label="'更多操作：' + item.title">
            •••
          </summary>
          <button
            v-if="archived"
            type="button"
            @click="selected = { route: item, action: 'restore' }"
          >
            恢复到仓库
          </button>
          <button
            v-else
            type="button"
            @click="selected = { route: item, action: item.canDelete ? 'delete' : 'archive' }"
          >
            {{ item.canDelete ? '永久删除草稿' : '移出仓库' }}
          </button>
        </details>
      </article>
    </div>
    <footer
      v-if="!error && total"
      class="route-pagination"
    >
      <span>共 {{ total }} 条路线</span><button
        type="button"
        class="outline-link"
        :disabled="page <= 1 || loading"
        @click="page--; load()"
      >
        上一页
      </button>
      <span>{{ page }} / {{ pageCount }}</span><button
        type="button"
        class="outline-link"
        :disabled="page >= pageCount || loading"
        @click="page++; load()"
      >
        下一页
      </button>
    </footer>
    <AppDialog
      v-if="creating"
      :title="official ? '新建官方路线' : '新建学习路线'"
      :busy="busy"
      @close="creating = false"
    >
      <form
        id="create-route-form"
        class="account-form"
        @submit.prevent="create"
      >
        <div class="form-field">
          <label for="new-route-title">路线标题</label><input
            id="new-route-title"
            v-model="newTitle"
            maxlength="200"
            placeholder="例如：Python 从入门到项目实践"
            autofocus
            :disabled="busy"
          >
        </div><p
          v-if="createError"
          class="form-error"
          role="alert"
        >
          {{ createError }}
        </p>
      </form>
      <template #footer>
        <button
          type="button"
          class="outline-link"
          :disabled="busy"
          @click="creating = false"
        >
          取消
        </button><button
          type="submit"
          form="create-route-form"
          class="primary-button"
          :disabled="busy"
        >
          {{ busy ? '正在创建…' : '创建并编辑' }}
        </button>
      </template>
    </AppDialog>
    <RoadmapActionDialog
      v-if="selected"
      :route="selected.route"
      :action="selected.action"
      @close="selected = null"
      @done="completed"
    />
    <AppDialog
      v-if="disabledRoute"
      title="下架原因"
      @close="disabledRoute = null"
    >
      <p class="dialog-route-title">
        {{ disabledRoute.title }}
      </p>
      <p class="readonly-text">
        {{ disabledRoute.disabledReason || '暂无原因说明，请联系管理员。' }}
      </p>
      <template #footer>
        <button
          type="button"
          class="outline-link"
          @click="disabledRoute = null"
        >
          关闭
        </button>
      </template>
    </AppDialog>
  </section>
</template>
