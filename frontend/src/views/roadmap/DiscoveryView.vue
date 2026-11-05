<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { changeFavorite, myFavorites, publicRoadmaps } from '../../api/roadmap'
import { useAuthStore } from '../../stores/auth'
import { difficultyName, formatDate } from '../../domain/roadmap'
import type { FavoriteItem } from '../../types/roadmap'
import AppIcon from '../../components/common/AppIcon.vue'
import UserAvatar from '../../components/common/UserAvatar.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const favorites = computed(() => route.name === 'favorites')
const query = ref('')
const difficulty = ref('')
const sortOptions = [
  { value: 'publishedAt:desc', label: '最新发布' },
  { value: 'publishedAt:asc', label: '最久发布' },
  { value: 'favoriteCount:desc', label: '收藏最多' },
  { value: 'favoriteCount:asc', label: '收藏最少' },
  { value: 'learnerCount:desc', label: '学习最多' },
  { value: 'learnerCount:asc', label: '学习最少' },
]
const sort = ref('publishedAt:desc')
const page = computed(() => Math.max(1, Math.min(1000000, Math.floor(Number(route.query.page) || 1))))
const items = ref<FavoriteItem[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const actionErrors = ref<Record<string, string>>({})
const busy = ref<string[]>([])
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / 12)))
let request = 0

async function load() {
  const ticket = ++request
  query.value = typeof route.query.q === 'string' ? route.query.q : ''
  difficulty.value = typeof route.query.difficulty === 'string' ? route.query.difficulty : ''
  const selectedSort = String(route.query.sortBy || 'publishedAt') + ':' + String(route.query.order || 'desc')
  sort.value = sortOptions.some(option => option.value === selectedSort) ? selectedSort : 'publishedAt:desc'
  loading.value = true; error.value = ''; actionErrors.value = {}; items.value = []; total.value = 0; busy.value = []
  try {
    if (favorites.value) {
      const result = await myFavorites({ page: page.value })
      if (ticket !== request) return
      items.value = result.items; total.value = result.total
    } else {
      const [sortBy, order] = sort.value.split(':')
      const result = await publicRoadmaps({ q: query.value, difficulty: difficulty.value || undefined, page: page.value, sortBy, order })
      if (ticket !== request) return
      items.value = result.items.map(card => ({ roadmapId: card.id, title: card.title, status: 'published',
        accessible: true, favoritedAt: '', roadmap: card }))
      total.value = result.total
    }
    if (page.value > pageCount.value) await navigate(pageCount.value)
  } catch (cause) { if (ticket === request) error.value = cause instanceof Error ? cause.message : '无法加载路线，请重试' }
  finally { if (ticket === request) loading.value = false }
}
function navigate(nextPage = 1) {
  const [sortBy, order] = sort.value.split(':')
  return router.push({ name: favorites.value ? 'favorites' : 'community', query: {
    ...(!favorites.value && query.value.trim() ? { q: query.value.trim() } : {}),
    ...(!favorites.value && difficulty.value ? { difficulty: difficulty.value } : {}),
    ...(!favorites.value && sort.value !== 'publishedAt:desc' ? { sortBy, order } : {}),
    ...(nextPage > 1 ? { page: String(nextPage) } : {}),
  } })
}
function reset() { query.value = ''; difficulty.value = ''; void navigate() }
async function toggle(item: FavoriteItem) {
  if (!auth.authenticated) { await router.push({ path: '/login' }); return }
  if (busy.value.includes(item.roadmapId)) return
  const ticket = request
  const viewer = auth.user?.id
  busy.value.push(item.roadmapId); actionErrors.value[item.roadmapId] = ''
  const enabled = !favorites.value && !item.roadmap?.isFavorited
  try {
    const result = await changeFavorite(item.roadmapId, enabled)
    if (ticket !== request || viewer !== auth.user?.id) return
    if (favorites.value) await load()
    else if (item.roadmap) {
      item.roadmap.isFavorited = result.isFavorited
      item.roadmap.favoriteCount = result.favoriteCount
      if (sort.value.startsWith('favoriteCount:')) await load()
    }
  } catch (cause) {
    if (ticket === request && viewer === auth.user?.id) actionErrors.value[item.roadmapId] = cause instanceof Error ? cause.message : '收藏操作失败，请重试'
  } finally { if (ticket === request) busy.value = busy.value.filter(id => id !== item.roadmapId) }
}
watch(() => [route.fullPath, auth.user?.id, auth.sessionVersion], () => { void load() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { request++ })
</script>

<template>
  <section
    class="discovery-page content-page route-library-layout fresh-discovery"
    :class="favorites ? 'favorites-page' : 'community-page'"
  >
    <header class="discovery-heading">
      <div>
        <p class="eyebrow">
          {{ favorites ? '我的收藏' : '探索 · 分享 · 成长' }}
        </p>
        <h1>{{ favorites ? '我的收藏' : '发现一条适合你的学习路线' }}</h1>
        <p>{{ favorites ? '把感兴趣的路线留在这里，随时回来看看。' : '从真实经验出发，找到方向，按自己的节奏前进。' }}</p>
      </div>
      <RouterLink
        v-if="favorites"
        class="outline-link"
        to="/"
      >发现更多路线 →</RouterLink>
    </header>
    <form
      v-if="!favorites"
      class="discovery-search"
      role="search"
      @submit.prevent="navigate()"
    >
      <label
        class="library-sr-only"
        for="community-keyword"
      >想学什么？</label>
      <div>
        <div class="library-search-field">
          <AppIcon name="search" />
          <input
            id="community-keyword"
            v-model="query"
            maxlength="200"
            placeholder="搜索路线标题，例如 Python、前端开发"
          >
          <button
            v-if="query"
            type="button"
            class="library-clear-search"
            aria-label="清空搜索关键词"
            @click="query = ''; navigate()"
          >
            <AppIcon name="close" />
          </button>
        </div>
        <button
          type="submit"
          class="primary-button"
        >
          搜索
        </button>
      </div>
      <div
        class="discovery-filter"
        aria-label="路线难度"
      >
        <button
          v-for="option in [{ value: '', label: '全部难度' }, { value: 'beginner', label: '入门' }, { value: 'intermediate', label: '进阶' }, { value: 'advanced', label: '高级' }]"
          :key="option.value"
          type="button"
          class="library-filter-chip"
          :aria-pressed="difficulty === option.value"
          @click="difficulty = option.value; navigate()"
        >
          {{ option.label }}
        </button>
      </div>
    </form>
    <div class="discovery-results-heading">
      <div><h2>{{ favorites ? '收藏的路线' : query || difficulty ? '搜索结果' : '全部路线' }}</h2><span v-if="!loading && !error">共 {{ total }} 条路线</span></div>
      <span
        v-if="favorites"
        class="library-sort-label"
      ><AppIcon name="clock" />最近收藏</span>
      <div
        v-else
        class="library-sort-control"
      >
        <label
          class="library-sr-only"
          for="community-sort"
        >路线排序</label>
        <select
          id="community-sort"
          v-model="sort"
          @change="navigate()"
        >
          <option
            v-for="option in sortOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
      </div>
    </div>
    <p
      v-if="loading"
      role="status"
      class="loading-message"
    >
      正在加载路线…
    </p>
    <div
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
    </div>
    <div
      v-else-if="!items.length"
      class="feature-placeholder"
    >
      <span class="placeholder-icon"><AppIcon :name="favorites ? 'bookmark' : 'compass'" /></span>
      <h2>{{ favorites ? '还没有收藏路线' : '暂时没有符合条件的路线' }}</h2>
      <p>{{ favorites ? '去社区发现感兴趣的路线，点击收藏就能在这里找到。' : '试试其他关键词或难度，也可以分享自己的第一条路线。' }}</p>
      <RouterLink
        v-if="favorites"
        to="/"
        class="outline-link"
      >去社区发现</RouterLink>
      <button
        v-else-if="query || difficulty"
        type="button"
        class="outline-link"
        @click="reset"
      >
        查看全部路线
      </button>
    </div>
    <div
      v-else
      class="discovery-grid"
      :aria-busy="loading"
    >
      <article
        v-for="item in items"
        :key="item.roadmapId"
        class="discovery-card"
        :class="{ restricted: !item.accessible }"
      >
        <template v-if="item.roadmap">
          <RouterLink
            :to="{ name: 'roadmap-detail', params: { id: item.roadmapId } }"
            class="discovery-card-link"
          >
            <span class="discovery-cover"><AppIcon name="repository" /></span>
            <div class="discovery-card-copy">
              <h3>{{ item.title }}</h3>
              <p>{{ item.roadmap.description || '暂无路线简介' }}</p>
              <div class="library-card-stats"><span class="difficulty-badge">{{ difficultyName(item.roadmap.difficulty) }}</span><span>{{ item.roadmap.stageCount }} 个阶段 · {{ item.roadmap.nodeCount }} 个节点</span></div>
            </div>
          </RouterLink>
          <div class="fresh-card-meta">
            <RouterLink
              :to="{ name: 'user-profile', params: { userId: item.roadmap.author.id } }"
              class="fresh-author"
              :aria-label="'查看' + (item.roadmap.author.nickname || item.roadmap.author.username) + '的个人主页'"
            >
              <UserAvatar
                :name="item.roadmap.author.nickname || item.roadmap.author.username"
                :src="item.roadmap.author.avatarUrl"
              />
              <span class="fresh-author-name">{{ item.roadmap.author.nickname || item.roadmap.author.username }}</span>
            </RouterLink>
            <span>V{{ item.roadmap.versionNo }}</span>
            <time :datetime="item.roadmap.publishedAt">{{ formatDate(item.roadmap.publishedAt) }}</time>
          </div>
          <footer class="discovery-card-footer">
            <div class="fresh-social-stats">
              <span>{{ item.roadmap.favoriteCount }} 人收藏</span><span>{{ item.roadmap.learnerCount }} 人学习</span>
            </div>
            <button
              v-if="!item.roadmap.isOwner"
              type="button"
              class="outline-link"
              :aria-pressed="favorites || item.roadmap.isFavorited"
              :aria-label="(favorites || item.roadmap.isFavorited ? '取消收藏：' : '收藏：') + item.title"
              :disabled="busy.includes(item.roadmapId)"
              @click="toggle(item)"
            >
              <AppIcon name="bookmark" />{{ busy.includes(item.roadmapId) ? '处理中…' : favorites ? '取消收藏' : item.roadmap.isFavorited ? '已收藏' : '收藏' }}
            </button>
            <RouterLink
              v-else
              :to="{ name: 'roadmap-detail', params: { id: item.roadmapId } }"
              class="outline-link"
            >管理路线</RouterLink>
          </footer>
        </template>
        <template v-else>
          <span class="discovery-cover restricted-cover"><AppIcon name="shield" /></span>
          <div class="restricted-copy">
            <h3>{{ item.title }}</h3><p>该路线暂不可访问，收藏记录仍为你保留。</p><time :datetime="item.favoritedAt">收藏于 {{ formatDate(item.favoritedAt) }}</time>
          </div>
          <footer class="discovery-card-footer">
            <button
              type="button"
              class="outline-link"
              :disabled="busy.includes(item.roadmapId)"
              @click="toggle(item)"
            >
              <AppIcon name="bookmark" />{{ busy.includes(item.roadmapId) ? '处理中…' : '取消收藏' }}
            </button>
          </footer>
        </template>
        <p
          v-if="actionErrors[item.roadmapId]"
          class="form-error"
          role="alert"
        >
          {{ actionErrors[item.roadmapId] }}
        </p>
      </article>
    </div>
    <footer
      v-if="!loading && !error && total"
      class="route-pagination"
    >
      <span>共 {{ total }} 条路线</span><button
        type="button"
        class="outline-link"
        :disabled="page <= 1"
        @click="navigate(page - 1)"
      >
        上一页
      </button><span>{{ page }} / {{ pageCount }}</span><button
        type="button"
        class="outline-link"
        :disabled="page >= pageCount"
        @click="navigate(page + 1)"
      >
        下一页
      </button>
    </footer>
  </section>
</template>

<style scoped>
.fresh-discovery { max-width: 1280px; margin: auto; padding: 48px 40px; }
.fresh-discovery .discovery-heading { text-align: left; justify-content: space-between; align-items: flex-start; margin-bottom: 32px; }
.fresh-discovery .eyebrow { font-size: 12px; letter-spacing: .1em; margin-bottom: 12px; }
.fresh-discovery .discovery-heading h1 { font-size: clamp(26px, 3vw, 38px); letter-spacing: -.04em; margin: 0 0 12px; }
.fresh-discovery .discovery-search { max-width: none; margin-bottom: 28px; }
.fresh-discovery .discovery-filter { justify-content: flex-start; margin-top: 20px; }
.fresh-discovery .library-filter-chip { border-radius: 24px; border-color: transparent; background: var(--surface-soft); }
.fresh-discovery .library-filter-chip[aria-pressed=true] { color: #fff; background: var(--library-accent); }
.fresh-discovery .discovery-results-heading { border: 0; padding: 0; margin-bottom: 20px; }
.fresh-discovery .discovery-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; }
.fresh-discovery .discovery-card { display: flex; flex-direction: column; flex-wrap: nowrap; align-items: stretch; gap: 0; height: auto; min-height: 320px; padding: 24px; border-radius: 12px; overflow: hidden; transition: border-color .18s; }
.fresh-discovery .discovery-card:hover { border-color: #91b8a5; box-shadow: none; }
.fresh-discovery .discovery-card-link { display: flex; flex: 1 0 auto; flex-direction: column; align-items: flex-start; gap: 18px; height: auto; width: 100%; }
.fresh-discovery .discovery-cover { width: 46px; height: 46px; border-radius: 10px; background: var(--library-soft); display: grid; place-items: center; }
.fresh-discovery .discovery-cover .app-icon { width: 25px; height: 25px; }
.fresh-discovery .discovery-card-copy { display: flex; flex-direction: column; gap: 12px; width: 100%; }
.fresh-discovery .discovery-card h3 { font-size: 19px; margin: 0; white-space: normal; overflow-wrap: anywhere; line-height: 1.5; }
.fresh-discovery .discovery-card-copy > p { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; white-space: normal; height: 48px; font-size: 14px; line-height: 24px; margin: 0; overflow: hidden; }
.fresh-discovery .library-card-stats { display: flex; flex-wrap: wrap; gap: 8px 12px; font-size: 12px; white-space: normal; overflow: visible; }
.fresh-card-meta { display: flex; align-items: center; gap: 8px; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--library-line); font-size: 12px; color: var(--library-muted); min-width: 0; width: 100%; }
.fresh-card-meta .user-avatar { width: 26px; height: 26px; flex-shrink: 0; }
.fresh-author { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; min-height: 44px; border-radius: 4px; }
.fresh-author-name { min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.fresh-author:hover .fresh-author-name { color: var(--library-accent); text-decoration: underline; text-underline-offset: 3px; }
.fresh-author:focus-visible { outline: 2px solid var(--library-accent); outline-offset: 3px; }
.fresh-card-meta time { font-size: 11px; white-space: nowrap; }
.fresh-discovery .discovery-card-footer { flex-direction: row; align-items: center; justify-content: space-between; gap: 12px; width: 100%; max-width: none; padding: 12px 0 0; margin-top: auto; }
.fresh-discovery .discovery-card-footer .outline-link { min-width: 0; min-height: 44px; padding: 8px 10px; font-size: 12px; gap: 6px; }
.fresh-social-stats { display: flex; flex: 1; flex-wrap: wrap; align-items: center; gap: 4px 12px; min-width: 0; font-size: 12px; }
.fresh-social-stats span { white-space: nowrap; }
.fresh-discovery .discovery-card-footer > .outline-link { flex: 0 0 auto; }
.fresh-discovery .restricted-copy { flex: 1; padding-top: 20px; }
@media (max-width: 1050px) { .fresh-discovery .discovery-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 650px) { .fresh-discovery { padding: 28px 20px; } .fresh-discovery .discovery-grid { grid-template-columns: minmax(0, 1fr); } .fresh-discovery .discovery-card { padding: 22px; } .fresh-discovery .discovery-heading h1 { font-size: 28px; } .fresh-discovery .library-search-field input { font-size: 16px; } .fresh-discovery .discovery-search .primary-button { min-width: 66px; } }
@media (prefers-reduced-motion: reduce) { .fresh-discovery .discovery-card { transition: none; } }
</style>
