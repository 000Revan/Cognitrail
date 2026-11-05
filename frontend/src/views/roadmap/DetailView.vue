<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { changeFavorite, roadmapDetail } from '../../api/roadmap'
import { ApiError } from '../../api/http'
import { roadmapSubscription } from '../../api/user'
import { useAuthStore } from '../../stores/auth'
import type { RoadmapDetail } from '../../types/roadmap'
import { difficultyName, formatDate } from '../../domain/roadmap'
import RoadmapCanvas from '../../components/roadmap/RoadmapCanvas.vue'
import RoadmapActionDialog from '../../components/roadmap/RoadmapActionDialog.vue'
import UserAvatar from '../../components/common/UserAvatar.vue'
import AppIcon from '../../components/common/AppIcon.vue'
import JoinLearningDialog from '../../components/roadmap/JoinLearningDialog.vue'
import ReportDialog from '../../components/common/ReportDialog.vue'
import type { EnrollmentSummary } from '../../types/enrollment'

const route = useRoute(), router = useRouter(), auth = useAuthStore()
const data = ref<RoadmapDetail | null>(null)
const loading = ref(false), error = ref(''), favoriteBusy = ref(false), favoriteError = ref('')
const joining = ref(false), versionOpen = ref(false)
const subscribed = ref<boolean | null>(null), subscriptionBusy = ref(false), subscriptionError = ref('')
const action = ref<'archive' | 'restore' | 'delete' | null>(null)
const maintain = computed(() => !!data.value && (data.value.canMaintain ?? data.value.isOwner))
const canBrowse = computed(() => maintain.value && !!data.value?.canReadContent && data.value.status !== 'disabled')
const canEdit = computed(() => maintain.value && data.value?.contentSource === 'draft' && !data.value.authorArchivedAt && ['draft', 'published'].includes(data.value.status))
const canDiscuss = computed(() => !!data.value?.releaseId && data.value.status !== 'disabled')
let request = 0

/** 页面入口统一，工作稿仍通过独立授权接口读取，不混入公开响应。 */
async function load() {
  const ticket = ++request, id = String(route.params.id)
  loading.value = true; error.value = ''; data.value = null; action.value = null
  favoriteBusy.value = false; favoriteError.value = ''; joining.value = versionOpen.value = false
  subscribed.value = null; subscriptionBusy.value = false; subscriptionError.value = ''
  try {
    let result: RoadmapDetail
    try { result = await roadmapDetail(id) }
    catch (cause) {
      if (ticket !== request) return
      if (!(auth.authenticated && cause instanceof ApiError && cause.status === 404)) throw cause
      result = await roadmapDetail(id, undefined, 'draft')
    }
    if (ticket !== request) return
    if ((result.canMaintain ?? result.isOwner) && result.contentSource !== 'draft') result = await roadmapDetail(id, undefined, 'draft')
    if (ticket === request) {
      data.value = result
      if (auth.authenticated && !(result.canMaintain ?? result.isOwner)) await loadSubscription(ticket, id)
    }
  } catch (cause) {
    if (ticket === request) error.value = cause instanceof Error ? cause.message : '无法加载路线'
  } finally { if (ticket === request) loading.value = false }
}
async function loadSubscription(ticket = request, id = String(route.params.id)) {
  subscriptionError.value = ''
  try { const result = await roadmapSubscription(id); if (ticket === request) subscribed.value = result.subscribed }
  catch (cause) { if (ticket === request) subscriptionError.value = cause instanceof Error ? cause.message : '订阅状态加载失败' }
}
async function toggleSubscription() {
  if (subscriptionBusy.value || subscribed.value === null) return
  const ticket = request
  subscriptionBusy.value = true; subscriptionError.value = ''
  try { const result = await roadmapSubscription(String(route.params.id), !subscribed.value); if (ticket === request) subscribed.value = result.subscribed }
  catch (cause) { if (ticket === request) subscriptionError.value = cause instanceof Error ? cause.message : '订阅操作失败' }
  finally { if (ticket === request) subscriptionBusy.value = false }
}
watch([() => route.fullPath, () => auth.user?.id, () => auth.sessionVersion], () => { void load() }, { immediate: true, flush: 'sync' })
function outsideVersion(event: PointerEvent) {
  if (!(event.target as Element).closest('.detail-version')) versionOpen.value = false
}
async function closeVersion() {
  versionOpen.value = false
  await nextTick(); window.document.getElementById('route-version-toggle')?.focus()
}
onMounted(() => window.addEventListener('pointerdown', outsideVersion))
onBeforeUnmount(() => { request++; window.removeEventListener('pointerdown', outsideVersion) })
function startLearning() {
  if (!auth.authenticated) { void router.push({ path: '/login' }); return }
  joining.value = true
}
function joined(value: EnrollmentSummary) { joining.value = false; void router.push({ name: 'learning-content', params: { id: value.id } }) }
function browseComponent(kind: 'stage' | 'node', id: string) {
  if (canBrowse.value) void router.push({ name: 'roadmap-browse', params: { id: route.params.id }, query: { [kind]: id } })
}
async function done() {
  if (action.value === 'delete') await router.replace('/roadmaps')
  else await load()
}
async function toggleFavorite() {
  if (!data.value || maintain.value || favoriteBusy.value) return
  if (!auth.authenticated) { await router.push({ path: '/login' }); return }
  const ticket = request, viewer = auth.sessionVersion
  favoriteBusy.value = true; favoriteError.value = ''
  try {
    const result = await changeFavorite(data.value.id, !data.value.isFavorited)
    if (ticket !== request || viewer !== auth.sessionVersion || !data.value) return
    data.value.isFavorited = result.isFavorited; data.value.favoriteCount = result.favoriteCount
  } catch (cause) {
    if (ticket === request && viewer === auth.sessionVersion) favoriteError.value = cause instanceof Error ? cause.message : '收藏操作失败'
  } finally { if (ticket === request) favoriteBusy.value = false }
}
</script>

<template>
  <section
    class="route-detail-page content-page"
    :aria-busy="loading"
  >
    <nav
      class="route-breadcrumb"
      aria-label="面包屑"
    >
      <RouterLink :to="maintain ? '/roadmaps' : '/'">{{ maintain ? '我的创作' : '社区发现' }}</RouterLink><span>/</span><span>路线详情</span>
    </nav>
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
        class="text-button"
        type="button"
        @click="load"
      >
        重新加载
      </button>
    </div>
    <template v-if="data">
      <article
        class="detail-overview"
        aria-label="路线信息"
      >
        <div class="detail-heading">
          <div class="detail-heading-copy">
            <div class="route-title-line">
              <h1>{{ data.title }}</h1>
              <span class="difficulty-badge">{{ difficultyName(data.difficulty) }}</span>
              <div
                v-if="data.versionNo"
                class="detail-version"
                @keydown.esc.stop.prevent="closeVersion"
              >
                <button
                  id="route-version-toggle"
                  class="version-badge version-toggle"
                  type="button"
                  :aria-expanded="versionOpen"
                  aria-controls="route-version-details"
                  @click="versionOpen = !versionOpen"
                >
                  {{ maintain ? '公开版 V' : 'V' }}{{ data.versionNo }}<AppIcon name="chevron" />
                </button>
                <section
                  v-if="versionOpen"
                  id="route-version-details"
                  class="version-popover"
                  role="region"
                  aria-label="版本说明"
                >
                  <header>
                    <h2>版本说明 · V{{ data.versionNo }}</h2><button
                      type="button"
                      aria-label="关闭版本说明"
                      @click="closeVersion"
                    >
                      ×
                    </button>
                  </header>
                  <time
                    v-if="data.publishedAt"
                    :datetime="data.publishedAt"
                  >{{ formatDate(data.publishedAt) }}</time>
                  <p>{{ data.updateSummary || '暂无版本说明' }}</p>
                </section>
              </div>
              <span
                v-if="maintain"
                class="route-badge"
                :class="data.status"
              >{{ data.authorArchivedAt ? '已归档' : data.displayStatus }}</span>
              <span
                v-if="maintain && data.versionNo && data.hasUnpublishedChanges"
                class="draft-change-label"
              >工作稿待发布</span>
            </div>
            <div class="detail-author">
              <RouterLink
                class="detail-author-link"
                :to="{ name: 'user-profile', params: { userId: data.author.id } }"
                :aria-label="'查看' + (data.author.nickname || data.author.username) + '的个人主页'"
              >
                <UserAvatar
                  :name="data.author.nickname || data.author.username"
                  :src="data.author.avatarUrl || (auth.user?.id === data.author.id ? auth.user.avatarUrl : null)"
                />
                <span class="detail-author-name">{{ data.author.nickname || data.author.username }}</span>
              </RouterLink>
              <time :datetime="data.updatedAt">更新于 {{ formatDate(data.updatedAt) }}</time>
            </div>
            <div
              class="detail-stats"
              aria-label="路线概况"
            >
              <div><AppIcon name="list" /><strong>{{ data.stageCount }}</strong><span>学习阶段</span></div>
              <div><AppIcon name="repository" /><strong>{{ data.nodeCount }}</strong><span>知识节点</span></div>
              <div><AppIcon name="user" /><strong>{{ data.learnerCount }}</strong><span>人学习</span></div>
              <div><AppIcon name="bookmark" /><strong>{{ data.favoriteCount }}</strong><span>人收藏</span></div>
            </div>
          </div>
          <div
            class="route-actions detail-actions"
            aria-label="路线操作"
          >
            <template v-if="maintain">
              <RouterLink
                v-if="canEdit"
                class="primary-button"
                :to="{ name: 'roadmap-editor', params: { id: data.id } }"
              ><AppIcon name="settings" />编辑工作稿</RouterLink>
              <RouterLink
                v-if="canBrowse"
                class="outline-link"
                :to="{ name: 'roadmap-browse', params: { id: data.id } }"
              ><AppIcon name="repository" />预览工作稿</RouterLink>
              <details class="detail-more">
                <summary aria-label="更多路线操作">
                  更多<AppIcon name="chevron" />
                </summary>
                <button
                  v-if="data.authorArchivedAt"
                  type="button"
                  @click="action = 'restore'"
                >
                  恢复到仓库
                </button>
                <button
                  v-else
                  type="button"
                  @click="action = data.canDelete ? 'delete' : 'archive'"
                >
                  {{ data.canDelete ? '删除草稿' : '归档路线' }}
                </button>
              </details>
            </template>
            <template v-else>
              <RouterLink
                v-if="data.learning"
                class="primary-button"
                :to="{ name: 'learning-content', params: { id: data.learning.id } }"
              >{{ data.learning.status === 'abandoned' ? '恢复原版学习' : '继续学习' }}</RouterLink>
              <button
                v-else-if="data.canStartLearning"
                type="button"
                class="primary-button"
                @click="startLearning"
              >
                <AppIcon name="compass" />开始学习
              </button>
              <button
                v-if="data.canFavorite"
                type="button"
                class="outline-link"
                :aria-pressed="data.isFavorited"
                :disabled="favoriteBusy"
                @click="toggleFavorite"
              >
                <AppIcon name="bookmark" />{{ favoriteBusy ? '处理中…' : data.isFavorited ? '取消收藏' : '收藏' }}
              </button>
              <button
                v-if="auth.authenticated"
                type="button"
                class="outline-link"
                :aria-pressed="subscribed ?? false"
                :disabled="subscriptionBusy || subscribed === null"
                @click="toggleSubscription"
              >
                {{ subscriptionBusy ? '处理中…' : subscribed ? '已订阅更新' : '订阅更新' }}
              </button>
              <p
                v-if="subscriptionError"
                class="form-error"
                role="alert"
              >
                {{ subscriptionError }} <button
                  v-if="subscribed === null"
                  type="button"
                  class="text-button"
                  @click="loadSubscription()"
                >
                  重试
                </button>
              </p>
            </template>
            <RouterLink
              v-if="canDiscuss"
              class="outline-link discussion-entry"
              :to="'/roadmaps/' + data.id + '/issues'"
            ><AppIcon name="list" />问题与反馈</RouterLink>
            <ReportDialog
              v-if="auth.authenticated && !maintain"
              with-trigger
              target-type="roadmap"
              :target-id="data.id"
              :target-title="data.title"
            />
            <p
              v-if="favoriteError"
              class="form-error"
              role="alert"
            >
              {{ favoriteError }}
            </p>
          </div>
        </div>
        <div class="detail-description-block">
          <p class="detail-description">
            {{ data.description || '暂无路线简介' }}
          </p>
          <p
            v-if="data.effortNote"
            class="detail-effort"
          >
            <AppIcon name="clock" />{{ data.effortNote }} · 仅供参考
          </p>
        </div>
      </article>
      <section
        class="detail-graph"
        aria-label="学习路线结构"
      >
        <header class="detail-graph-heading">
          <h2>学习路线</h2><span>{{ data.stageCount }} 个阶段 · {{ data.nodeCount }} 个节点</span>
        </header>
        <RoadmapCanvas
          :stages="data.stages"
          :connections="data.connections"
          :selectable="canBrowse"
          @select="browseComponent"
        />
      </section>
    </template>
    <RoadmapActionDialog
      v-if="data && action"
      :route="data"
      :action="action"
      @close="action = null"
      @done="done"
    />
    <JoinLearningDialog
      v-if="joining && data?.releaseId && data.versionNo"
      :roadmap-id="data.id"
      :release-id="data.releaseId"
      :version-no="data.versionNo"
      @close="joining = false"
      @refresh="load"
      @done="joined"
    />
  </section>
</template>

<style scoped>
.route-detail-page { max-width: 1240px; padding: 36px 36px 64px; margin: auto; }
.route-breadcrumb { display: flex; gap: 12px; align-items: center; margin: 0 0 24px; font-size: 13px; color: var(--muted); }
.route-breadcrumb a { min-height: 32px; display: inline-flex; align-items: center; }
.detail-overview { border: 1px solid var(--line); border-radius: 14px; background: var(--paper); }
.detail-overview .detail-heading { display: grid; grid-template-columns: minmax(0, 1fr) 260px; align-items: start; gap: 36px; padding: 30px 32px; margin: 0; border: 0; border-radius: 0; background: transparent; }
.detail-heading-copy { min-width: 0; }
.route-title-line { gap: 10px; align-items: center; }
.detail-heading h1 { flex-basis: 100%; margin: 0 0 8px; font-size: clamp(24px, 2.5vw, 32px); line-height: 1.45; letter-spacing: -.6px; overflow-wrap: anywhere; text-wrap: balance; }
.difficulty-badge { font-size: 12px; padding: 5px 10px; }
.route-badge { font-size: 11px; }
.draft-change-label { font-size: 11px; color: var(--muted); }
.detail-version { position: relative; }
.version-toggle { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 5px 10px; border: 1px solid var(--line); color: var(--green); background: var(--paper); cursor: pointer; font: inherit; font-size: 12px; }
.version-toggle .app-icon { width: 12px; height: 12px; }
.version-toggle[aria-expanded=true] { background: var(--green-soft); }
.version-popover { position: absolute; left: 0; top: calc(100% + 8px); width: min(340px, calc(100vw - 96px)); max-height: 300px; overflow: auto; z-index: 20; padding: 18px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); box-shadow: 0 10px 30px #193f2d14; }
.version-popover header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.version-popover h2 { margin: 0; font-size: 14px; }
.version-popover header button { border: 0; background: transparent; color: var(--muted); font-size: 22px; min-width: 32px; min-height: 32px; cursor: pointer; }
.version-popover time { display: block; margin-top: 6px; color: var(--muted); font-size: 12px; }
.version-popover p { margin: 14px 0 0; font-size: 13px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.detail-author { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 20px; margin: 18px 0 14px; color: var(--muted); font-size: 12px; }
.detail-author-link { display: inline-flex; align-items: center; gap: 9px; min-height: 40px; min-width: 0; color: var(--ink); border-radius: 4px; }
.detail-author-link :deep(.user-avatar) { width: 32px; height: 32px; flex-shrink: 0; }
.detail-author-name { overflow-wrap: anywhere; }
.detail-author-link:hover .detail-author-name { color: var(--green); text-decoration: underline; text-underline-offset: 3px; }
.detail-stats { display: flex; flex-wrap: wrap; gap: 12px 24px; padding: 0; margin: 0; }
.detail-stats > div { display: inline-flex; align-items: center; justify-content: flex-start; gap: 6px; border: 0; border-radius: 0; padding: 0; min-width: 0; background: none; font-size: 12px; color: var(--muted); }
.detail-stats strong { font-size: 15px; font-weight: 600; color: var(--ink); }
.detail-stats .app-icon { width: 15px; height: 15px; color: var(--green); }
.detail-heading .detail-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; width: 100%; max-width: none; padding-top: 8px; }
.detail-actions > .primary-button { grid-column: 1 / -1; }
.detail-actions > a, .detail-actions > button { min-width: 0; min-height: 44px; justify-content: center; font-size: 13px; padding: 9px 10px; }
.detail-actions .app-icon { width: 16px; height: 16px; }
.detail-actions .form-error { grid-column: 1 / -1; margin: 0; font-size: 12px; }
.detail-more { position: relative; width: 100%; }
.detail-more summary { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; padding: 9px 12px; border: 1px solid var(--line); border-radius: var(--radius-control); font-size: 13px; cursor: pointer; list-style: none; }
.detail-more summary::-webkit-details-marker { display: none; }
.detail-more[open] summary { background: var(--green-soft); }
.detail-more button { z-index: 10; }
.discussion-entry { color: var(--green); }
.detail-description-block { border-top: 1px solid var(--line); padding: 24px 32px; }
.detail-description { margin: 0; font-size: 14px; line-height: 1.95; white-space: pre-wrap; overflow-wrap: anywhere; }
.detail-effort { display: flex; align-items: center; gap: 8px; margin: 16px 0 0; color: var(--muted); font-size: 12px; }
.detail-effort .app-icon { width: 14px; height: 14px; }
.detail-graph { margin-top: 24px; padding: 0; border: 1px solid var(--line); border-radius: 14px; overflow: hidden; background: var(--paper); }
.detail-graph-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px 20px; padding: 22px 28px; border-bottom: 1px solid var(--line); }
.detail-graph-heading h2 { margin: 0; font-size: 18px; font-weight: 600; }
.detail-graph-heading span { font-size: 12px; color: var(--muted); }
.detail-graph :deep(.roadmap-canvas) { border: 0; border-radius: 0; }
.detail-graph :deep(.canvas-viewport) { height: 460px; }
.route-detail-page a:focus-visible, .route-detail-page button:focus-visible, .detail-more summary:focus-visible { outline: 2px solid var(--green); outline-offset: 3px; }
@media (max-width: 760px) {
  .route-detail-page { padding: 24px 20px 40px; }
  .detail-overview .detail-heading { grid-template-columns: minmax(0, 1fr); padding: 24px 22px; gap: 20px; }
  .detail-heading h1 { font-size: 25px; }
  .detail-author { gap: 8px 16px; }
  .detail-author time { width: 100%; }
  .detail-stats { gap: 12px 18px; }
  .detail-heading .detail-actions { padding-top: 0; }
  .detail-description-block { padding: 22px; }
  .detail-graph-heading { padding: 20px; }
  .detail-graph :deep(.canvas-viewport) { height: 390px; }
  .version-popover { left: -70px; width: min(300px, calc(100vw - 84px)); }
}
.detail-actions > :deep(.report-action-menu){grid-column:1/-1;justify-self:end}
</style>
