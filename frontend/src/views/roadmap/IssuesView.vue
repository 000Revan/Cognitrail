<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createIssue, getIssue, getReplies, issueAction, listIssues } from '../../api/issue'
import type { Comment, Issue, IssueDetail, IssueStatus } from '../../api/issue'
import { useAuthStore } from '../../stores/auth'
import { formatDate } from '../../domain/roadmap'
import DiscussionBody from '../../components/common/DiscussionBody.vue'
import UserAvatar from '../../components/common/UserAvatar.vue'
import AppDialog from '../../components/common/AppDialog.vue'
import AppIcon from '../../components/common/AppIcon.vue'
import ReportDialog from '../../components/common/ReportDialog.vue'

const route = useRoute(), router = useRouter(), auth = useAuthStore()
const roadmap = computed(() => String(route.params.id))
const issueId = computed(() => String(route.params.issueId || ''))
const prefix = computed(() => '/roadmaps/' + roadmap.value + '/issues')
const rows = ref<Issue[]>([]), detail = ref<IssueDetail | null>(null), roadmapTitle = ref('')
const page = ref(1), total = ref(0), topicCount = ref(0), closedCount = ref(0)
const filter = ref<IssueStatus | ''>(''), sort = ref('createdAt:desc')
const loading = ref(false), busy = ref(false), error = ref('')
type ActionScope = 'topic' | 'reply' | 'state' | 'subscription' | 'delete'
const actionErrors = ref<Partial<Record<ActionScope, string>>>({})
const threadErrors = ref<Record<string, string>>({})
const canManageState = computed(() => !!auth.user?.id && detail.value?.roadmapCreatorId === auth.user.id && detail.value.canResolve)
const composing = ref(false), editing = ref(false), title = ref(''), body = ref('')
const reply = ref(''), replyTo = ref<Comment | null>(null), replyRoot = ref(''), editComment = ref<Comment | null>(null)
const stateChoice = ref<IssueStatus | ''>(''), reason = ref(''), deleting = ref<string | null>(null)
const sidebar = ref<'actions' | 'timeline'>('actions'), expanded = ref<Record<string, boolean>>({})
const threadBusy = ref<Record<string, boolean>>({})
const names: Record<IssueStatus, string> = { open: '未处理', resolved: '已处理', closed: '已关闭' }
const eventNames: Record<string, string> = { created: '发起话题', edited: '编辑话题', resolved: '标记已处理', closed: '关闭话题', reopened: '重新打开' }
const commentsTotal = computed(() => detail.value?.commentCount ?? detail.value?.comments.total ?? 0)
let generation = 0
function clearForms() {
  actionErrors.value = {}
  composing.value = editing.value = false; title.value = body.value = reply.value = ''
  replyTo.value = editComment.value = null; replyRoot.value = ''
  stateChoice.value = ''; reason.value = ''; deleting.value = null
}
function queryPage() {
  return /^[1-9][0-9]{0,5}$/.test(String(route.query.page || '')) ? Number(route.query.page) : 1
}
async function load(reset = false) {
  const ticket = ++generation
  if (reset) {
    clearForms(); rows.value = []; detail.value = null; busy.value = false; roadmapTitle.value = ''
    expanded.value = {}; threadBusy.value = {}; threadErrors.value = {}; sidebar.value = 'actions'; page.value = queryPage()
    filter.value = ['open', 'resolved', 'closed'].includes(String(route.query.status)) ? route.query.status as IssueStatus : ''
    sort.value = ['createdAt:asc', 'createdAt:desc', 'lastActivityAt:desc'].includes(String(route.query.sort)) ? String(route.query.sort) : 'createdAt:desc'
  }
  error.value = ''; loading.value = true
  try {
    if (issueId.value) {
      const anchor = typeof route.query.commentId === 'string' ? route.query.commentId : undefined
      const result = await getIssue(roadmap.value, issueId.value, { page: page.value, commentId: anchor })
      if (ticket !== generation) return
      detail.value = result; page.value = result.comments.page; roadmapTitle.value = result.roadmapTitle || ''
      if (anchor) {
        for (const root of result.comments.items) if (root.replies?.items.some(r => r.id === anchor)) expanded.value[root.id] = true
        await nextTick()
        if (ticket === generation) document.getElementById('comment-' + anchor)?.scrollIntoView({ block: 'center' })
      }
    } else {
      const [sortBy, order] = sort.value.split(':')
      const result = await listIssues(roadmap.value, { page: page.value, status: filter.value || undefined, sortBy, order })
      if (ticket !== generation) return
      rows.value = result.items; total.value = result.total
      topicCount.value = result.topicCount ?? result.total; closedCount.value = result.closedCount ?? 0
      roadmapTitle.value = result.roadmapTitle || ''
    }
  } catch (cause) {
    if (ticket === generation) { detail.value = null; rows.value = []; error.value = cause instanceof Error ? cause.message : '加载失败，请重试' }
  } finally { if (ticket === generation) loading.value = false }
}
watch([() => route.fullPath, () => auth.sessionVersion, () => auth.user?.id], () => void load(true), { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++ })

async function mutate(work: () => Promise<unknown>, after?: (value: unknown) => Promise<void>, scope: ActionScope = 'topic') {
  if (busy.value) return
  const ticket = generation; busy.value = true; actionErrors.value[scope] = ''
  try {
    const value = await work()
    if (ticket !== generation) return
    clearForms(); busy.value = false
    if (after) await after(value)
    else await load()
  } catch (cause) { if (ticket === generation) actionErrors.value[scope] = cause instanceof Error ? cause.message : '操作失败，请重试' }
  finally { if (ticket === generation) busy.value = false }
}
async function submitTopic() {
  if (!title.value.trim() || !body.value.trim()) return
  const rid = roadmap.value, iid = issueId.value, text = title.value, content = body.value
  if (editing.value && detail.value) {
    const expectedUpdatedAt = detail.value.updatedAt
    await mutate(() => issueAction(rid, iid, '', { title: text, body: content, expectedUpdatedAt }, 'patch'))
  } else {
    await mutate(() => createIssue(rid, text, content), async value => {
      await router.push(prefix.value + '/' + (value as Issue).id)
    })
  }
}
function beginEdit() {
  if (!detail.value) return
  title.value = detail.value.title; body.value = detail.value.body || ''; editing.value = true
}
async function beginReply(item: Comment, root: Comment, edit = false) {
  replyTo.value = edit ? null : item; editComment.value = edit ? item : null
  replyRoot.value = root.id; reply.value = edit ? item.body || '' : ''
  expanded.value[root.id] = true
  await nextTick(); document.getElementById('comment-body')?.focus()
}
function cancelReply() { replyTo.value = editComment.value = null; replyRoot.value = ''; reply.value = '' }
watch(reply, () => { actionErrors.value.reply = '' })
watch([title, body], () => { actionErrors.value.topic = '' })
watch([stateChoice, reason], () => { actionErrors.value.state = '' })
watch(deleting, () => { actionErrors.value.delete = '' })
async function sidebarKeys(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  sidebar.value = event.key === 'Home' ? 'actions' : event.key === 'End' ? 'timeline' : sidebar.value === 'actions' ? 'timeline' : 'actions'
  await nextTick(); document.getElementById(sidebar.value === 'actions' ? 'actions-tab' : 'timeline-tab')?.focus()
}
async function submitReply() {
  if (!reply.value.trim()) return
  const rid = roadmap.value, iid = issueId.value, content = reply.value, target = replyTo.value, edited = editComment.value
  await mutate(() => edited
    ? issueAction(rid, iid, '/comments/' + edited.id, { body: content, expectedUpdatedAt: edited.updatedAt }, 'patch')
    : issueAction(rid, iid, '/comments', { body: content, replyToCommentId: target?.id || null }),
  async value => {
    const anchor = edited?.id || (value as { commentId?: string }).commentId
    if (anchor && route.query.commentId !== anchor) await router.replace({ path: route.path, query: { commentId: anchor }, hash: '#comment-' + anchor })
    else await load()
  }, 'reply')
}
async function changeState() {
  if (!detail.value || !stateChoice.value || !canManageState.value) return
  const data = { status: stateChoice.value, expectedStatus: detail.value.status, reason: reason.value.trim() || null }
  await mutate(() => issueAction(roadmap.value, issueId.value, '/state', data, 'patch'), undefined, 'state')
}
async function remove() {
  const target = deleting.value
  if (target) await mutate(() => issueAction(roadmap.value, issueId.value, target === 'topic' ? '' : '/comments/' + target, undefined, 'delete'), async () => {
    if (route.query.commentId) await router.replace({ path: route.path, query: { page: String(page.value) } })
    else await load()
  }, 'delete')
}
async function changeList() {
  await router.push({ path: prefix.value, query: { ...(filter.value ? { status: filter.value } : {}), ...(sort.value !== 'createdAt:desc' ? { sort: sort.value } : {}) } })
}
async function changePage(delta: number) {
  await router.push({ path: route.path, query: { ...(!issueId.value ? route.query : {}), page: String(page.value + delta) }, hash: '' })
}
function visibleReplies(root: Comment) {
  const replies = (root.replies?.items || []).filter(item => item.visibility !== 'deleted')
  return expanded.value[root.id] ? replies : replies.slice(0, 2)
}
function threadEntries(root: Comment) { return [root, ...visibleReplies(root)].filter(item => item.visibility !== 'deleted') }
async function threadPage(root: Comment, targetPage: number) {
  if (threadBusy.value[root.id]) return
  const ticket = generation
  threadBusy.value[root.id] = true; threadErrors.value[root.id] = ''
  try {
    const result = await getReplies(roadmap.value, issueId.value, root.id, targetPage)
    if (ticket === generation) { root.replies = result; expanded.value[root.id] = true }
  } catch (cause) { if (ticket === generation) threadErrors.value[root.id] = cause instanceof Error ? cause.message : '回复加载失败' }
  finally { if (ticket === generation) threadBusy.value[root.id] = false }
}
async function expandThread(root: Comment) {
  expanded.value[root.id] = true
  if (!root.replies?.items.length && root.replies?.total) await threadPage(root, 1)
}
</script>

<template>
  <section
    class="content-page discussion-page"
    :aria-busy="loading || busy"
  >
    <nav
      class="discussion-breadcrumb"
      aria-label="面包屑"
    >
      <RouterLink :to="'/roadmaps/' + roadmap"><AppIcon name="arrow" />{{ roadmapTitle || '路线详情' }}</RouterLink>
      <span>/</span><RouterLink
        v-if="issueId"
        :to="prefix"
      >问题与反馈</RouterLink><span v-else>问题与反馈</span>
    </nav>
    <header class="discussion-heading">
      <div>
        <h1>{{ issueId ? detail?.title || '话题详情' : '问题与反馈' }}</h1><span
          v-if="detail"
          class="topic-heading-meta"
        >#{{ detail.id }}<span
          class="issue-status"
          :data-status="detail.status"
        ><i />{{ names[detail.status] }}</span></span>
      </div>
      <button
        v-if="!issueId"
        class="primary-button new-topic-button"
        :disabled="loading || busy"
        @click="composing = true"
      >
        <span aria-hidden="true">＋</span>新建话题
      </button>
      <div
        v-else
        class="topic-heading-actions"
      >
        <RouterLink
          class="back-to-topics"
          :to="prefix"
        ><AppIcon name="list" />全部话题</RouterLink><ReportDialog
          v-if="detail?.visibility === 'public' && detail.author?.id !== auth.user?.id"
          with-trigger
          target-type="issue"
          :target-id="detail.id"
          :target-title="detail.title"
        />
      </div>
    </header>
    <div
      v-if="error"
      class="discussion-error"
      role="alert"
    >
      {{ error }}<button
        class="text-button"
        :disabled="busy"
        @click="load()"
      >
        重新加载
      </button>
    </div>
    <p
      v-if="loading"
      class="discussion-loading"
      role="status"
    >
      正在加载…
    </p>

    <div
      v-if="!issueId"
      class="topic-board"
    >
      <div class="topic-toolbar">
        <div class="topic-statistics">
          <button
            :class="{ active: !filter }"
            :disabled="loading"
            @click="filter = ''; changeList()"
          >
            <AppIcon name="list" /><strong>{{ topicCount }}</strong>话题
          </button><button
            :class="{ active: filter === 'closed' }"
            :disabled="loading"
            @click="filter = filter === 'closed' ? '' : 'closed'; changeList()"
          >
            <AppIcon name="check" /><strong>{{ closedCount }}</strong>已关闭
          </button>
        </div>
        <div class="topic-filters">
          <label><span>状态</span><select
            v-model="filter"
            aria-label="处理状态筛选"
            :disabled="loading"
            @change="changeList"
          ><option value="">全部状态</option><option value="open">未处理</option><option value="resolved">已处理</option><option value="closed">已关闭</option></select></label><label><AppIcon name="clock" /><select
            v-model="sort"
            aria-label="话题时间排序"
            :disabled="loading"
            @change="changeList"
          ><option value="createdAt:desc">最新发布</option><option value="createdAt:asc">最早发布</option><option value="lastActivityAt:desc">最近活跃</option></select></label>
        </div>
      </div>
      <div
        v-if="!loading && !error && !rows.length"
        class="topic-empty"
      >
        <AppIcon name="repository" /><h2>还没有话题</h2><button
          class="text-button"
          @click="composing = true"
        >
          发起第一个话题
        </button>
      </div>
      <article
        v-for="item in rows"
        :key="item.id"
        class="topic-row"
      >
        <span
          class="topic-state-icon"
          :data-status="item.status"
        ><AppIcon :name="item.status === 'open' ? 'compass' : 'check'" /></span>
        <div class="topic-row-content">
          <RouterLink
            class="topic-title"
            :to="prefix + '/' + item.id"
          >{{ item.title }}</RouterLink><div class="topic-row-meta">
            <span>#{{ item.id }}</span><RouterLink
              v-if="item.author"
              :to="'/users/' + item.author.id"
            ><UserAvatar
              :name="item.author.nickname"
              :src="item.author.avatarUrl"
            />{{ item.author.nickname }}</RouterLink><time>{{ formatDate(item.createdAt) }}</time>
          </div>
        </div>
        <div class="topic-row-end">
          <span
            class="issue-status"
            :data-status="item.status"
          ><i />{{ names[item.status] }}</span><RouterLink
            class="topic-reply-count"
            :to="prefix + '/' + item.id + '#comments'"
            :aria-label="item.title + '，' + (item.commentCount || 0) + '条评论'"
          ><svg
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          ><path d="M20 11a8 8 0 0 1-8 8H5l-4 3V11a9 9 0 0 1 19 0Z" /></svg>{{ item.commentCount || 0 }}</RouterLink>
        </div>
      </article>
      <nav
        v-if="total > 20"
        class="discussion-pagination"
        aria-label="话题分页"
      >
        <button
          :disabled="page <= 1 || loading"
          @click="changePage(-1)"
        >
          上一页
        </button><span>{{ page }} / {{ Math.ceil(total / 20) }}</span><button
          :disabled="page * 20 >= total || loading"
          @click="changePage(1)"
        >
          下一页
        </button>
      </nav>
    </div>

    <div
      v-else-if="detail && !loading"
      class="topic-detail-layout"
    >
      <div class="topic-main">
        <article class="topic-content-block">
          <header class="topic-author-bar">
            <RouterLink
              v-if="detail.author"
              class="topic-author"
              :to="'/users/' + detail.author.id"
            ><UserAvatar
              :name="detail.author.nickname"
              :src="detail.author.avatarUrl"
            /><strong>{{ detail.author.nickname }}</strong></RouterLink><span v-else>话题已删除</span><span class="author-role-label">发起者</span><time>{{ formatDate(detail.createdAt) }}</time>
          </header>
          <DiscussionBody
            class="discussion-body topic-content"
            :text="detail.body ?? '此话题已删除。'"
          />
        </article>

        <section
          id="comments"
          class="topic-comments-block"
          aria-labelledby="comments-title"
        >
          <header class="comments-heading">
            <h2 id="comments-title">
              评论 <span>{{ commentsTotal }}</span>
            </h2><span>按时间顺序</span>
          </header>
          <form
            v-if="detail.visibility === 'public' && detail.status !== 'closed' && !replyTo && !editComment"
            class="comment-composer main-composer"
            @submit.prevent="submitReply"
          >
            <UserAvatar
              :name="auth.user?.nickname || '我'"
              :src="auth.user?.avatarUrl"
            /><div class="composer-content">
              <label
                class="sr-only"
                for="comment-body"
              >回复正文</label><textarea
                id="comment-body"
                v-model="reply"
                placeholder="写下你的评论…"
                rows="3"
                maxlength="20000"
                required
                :disabled="busy"
              /><p
                v-if="actionErrors.reply"
                class="form-error"
                role="alert"
              >
                {{ actionErrors.reply }}
              </p><div class="composer-footer">
                <button
                  class="primary-button"
                  :disabled="busy || !reply.trim()"
                >
                  {{ busy ? '发送中…' : '发送回复' }}
                </button>
              </div>
            </div>
          </form>
          <p
            v-if="detail.status === 'closed'"
            class="discussion-closed"
          >
            <AppIcon name="shield" />话题已关闭
          </p>
          <p
            v-if="!detail.comments.items.length"
            class="comments-empty"
          >
            暂无评论
          </p>
          <article
            v-for="root in detail.comments.items"
            :key="root.id"
            class="comment-thread"
            :data-thread-id="root.id"
          >
            <div
              v-for="item in threadEntries(root)"
              :id="'comment-' + item.id"
              :key="item.id"
              class="comment-entry"
              :class="{ 'child-reply': item.id !== root.id }"
            >
              <RouterLink
                v-if="item.author"
                class="comment-avatar"
                :to="'/users/' + item.author.id"
                :aria-label="'查看' + item.author.nickname + '的主页'"
              ><UserAvatar
                :name="item.author.nickname"
                :src="item.author.avatarUrl"
              /></RouterLink><span
                v-else
                class="comment-avatar removed-avatar"
              ><UserAvatar name="内容不可见" /></span>
              <div class="comment-copy">
                <div class="comment-byline">
                  <RouterLink
                    v-if="item.author"
                    :to="'/users/' + item.author.id"
                  >{{ item.author.nickname }}</RouterLink><span v-else>内容不可见</span><span
                    v-if="item.author?.id === detail.author?.id"
                    class="comment-role"
                  >发起者</span><span
                    v-if="item.replyToCommentId && item.id !== root.id"
                    class="reply-target"
                  >回复 <RouterLink
                    v-if="item.replyToAuthor"
                    :to="'/users/' + item.replyToAuthor.id"
                  >@{{ item.replyToAuthor.nickname }}</RouterLink><span v-else>原回复对象</span></span>
                </div>
                <DiscussionBody
                  class="discussion-body comment-text"
                  :text="item.body ?? '此评论已隐藏'"
                />
                <div class="comment-meta">
                  <time>{{ formatDate(item.createdAt) }}</time><button
                    v-if="detail.visibility === 'public' && detail.status !== 'closed' && item.visibility === 'public'"
                    :disabled="busy"
                    @click="beginReply(item, root)"
                  >
                    回复
                  </button><button
                    v-if="item.canEdit && detail.visibility === 'public'"
                    :disabled="busy"
                    @click="beginReply(item, root, true)"
                  >
                    编辑
                  </button><button
                    v-if="item.canEdit && detail.visibility === 'public'"
                    class="comment-delete"
                    :disabled="busy"
                    @click="deleting = item.id"
                  >
                    删除
                  </button>
                  <ReportDialog
                    v-if="item.visibility === 'public' && item.author?.id !== auth.user?.id"
                    with-trigger
                    target-type="comment"
                    :target-id="item.id"
                    :target-title="item.body || undefined"
                  />
                </div>
              </div>
            </div>
            <p
              v-if="threadErrors[root.id]"
              class="form-error"
              role="alert"
            >
              {{ threadErrors[root.id] }} <button
                class="text-button"
                @click="threadPage(root, root.replies?.page || 1)"
              >
                重试
              </button>
            </p>
            <div
              v-if="root.replies?.total"
              class="thread-controls"
            >
              <button
                v-if="!expanded[root.id] && root.replies.total > 2"
                :disabled="threadBusy[root.id]"
                @click="expandThread(root)"
              >
                展开全部 {{ root.replies.total }} 条回复 <AppIcon name="chevron" />
              </button><template v-if="expanded[root.id]">
                <button
                  v-if="root.replies.page > 1"
                  :disabled="threadBusy[root.id]"
                  @click="threadPage(root, root.replies.page - 1)"
                >
                  上一页回复
                </button><span v-if="root.replies.total > root.replies.pageSize">{{ root.replies.page }} / {{ Math.ceil(root.replies.total / root.replies.pageSize) }}</span><button
                  v-if="root.replies.page * root.replies.pageSize < root.replies.total"
                  :disabled="threadBusy[root.id]"
                  @click="threadPage(root, root.replies.page + 1)"
                >
                  下一页回复
                </button><button @click="expanded[root.id] = false">
                  收起
                </button>
              </template>
            </div>
            <form
              v-if="replyRoot === root.id && (replyTo || editComment)"
              class="comment-composer inline-composer"
              @submit.prevent="submitReply"
            >
              <div class="composer-content">
                <label for="comment-body">{{ editComment ? '编辑回复' : '回复 @' + (replyTo?.author?.nickname || '用户') }}</label><textarea
                  id="comment-body"
                  v-model="reply"
                  rows="3"
                  maxlength="20000"
                  required
                  :disabled="busy"
                /><p
                  v-if="actionErrors.reply"
                  class="form-error"
                  role="alert"
                >
                  {{ actionErrors.reply }}
                </p><div class="composer-footer">
                  <button
                    type="button"
                    class="quiet-button"
                    :disabled="busy"
                    @click="cancelReply"
                  >
                    取消
                  </button><button
                    class="primary-button"
                    :disabled="busy || !reply.trim()"
                  >
                    {{ busy ? '发送中…' : editComment ? '保存回复' : '发送回复' }}
                  </button>
                </div>
              </div>
            </form>
          </article>
          <nav
            v-if="detail.comments.total > 20"
            class="discussion-pagination"
            aria-label="评论分页"
          >
            <button
              :disabled="page <= 1 || loading"
              @click="changePage(-1)"
            >
              上一页
            </button><span>{{ page }} / {{ Math.ceil(detail.comments.total / 20) }}</span><button
              :disabled="page * 20 >= detail.comments.total || loading"
              @click="changePage(1)"
            >
              下一页
            </button>
          </nav>
        </section>
      </div>

      <aside
        class="topic-sidebar"
        aria-label="话题管理"
      >
        <div
          class="sidebar-tabs"
          role="tablist"
          aria-label="话题侧栏"
          @keydown="sidebarKeys"
        >
          <button
            id="actions-tab"
            role="tab"
            :aria-selected="sidebar === 'actions'"
            :tabindex="sidebar === 'actions' ? 0 : -1"
            aria-controls="topic-actions"
            @click="sidebar = 'actions'"
          >
            操作
          </button><button
            id="timeline-tab"
            role="tab"
            :aria-selected="sidebar === 'timeline'"
            :tabindex="sidebar === 'timeline' ? 0 : -1"
            aria-controls="topic-timeline"
            @click="sidebar = 'timeline'"
          >
            时间线
          </button>
        </div>
        <section
          v-if="sidebar === 'actions'"
          id="topic-actions"
          role="tabpanel"
          aria-labelledby="actions-tab"
        >
          <div class="sidebar-section">
            <h2>话题状态</h2><span
              class="issue-status"
              :data-status="detail.status"
            ><i />{{ names[detail.status] }}</span>
          </div>
          <form
            v-if="canManageState && detail.visibility === 'public'"
            class="sidebar-section state-form"
            @submit.prevent="changeState"
          >
            <label for="issue-state">处理话题</label><select
              id="issue-state"
              v-model="stateChoice"
              aria-label="目标状态"
              :disabled="busy"
            >
              <option value="">
                选择操作
              </option><option
                v-if="detail.status !== 'open'"
                value="open"
              >
                设为未处理
              </option><option
                v-if="detail.status === 'open'"
                value="resolved"
              >
                标记已处理
              </option><option
                v-if="detail.status !== 'closed'"
                value="closed"
              >
                关闭话题
              </option>
            </select><template v-if="stateChoice">
              <label
                class="state-reason-label"
                for="state-reason"
              >处理原因{{ stateChoice === 'closed' ? '（必填）' : '（选填）' }}</label><textarea
                id="state-reason"
                v-model="reason"
                rows="3"
                maxlength="500"
                :required="stateChoice === 'closed'"
                :disabled="busy"
              />
            </template><button
              class="side-save"
              :disabled="busy || !stateChoice || stateChoice === 'closed' && !reason.trim()"
            >
              保存状态
            </button><p
              v-if="actionErrors.state"
              class="form-error"
              role="alert"
            >
              {{ actionErrors.state }}
            </p>
          </form>
          <div
            v-if="detail.visibility === 'public'"
            class="sidebar-section side-actions"
          >
            <h2>参与与管理</h2><button
              :aria-pressed="detail.subscribed"
              :disabled="busy"
              @click="mutate(() => issueAction(roadmap, issueId, '/subscription', { subscribed: !detail!.subscribed }, 'put'), undefined, 'subscription')"
            >
              <AppIcon name="bookmark" />{{ detail.subscribed ? '取消订阅' : '订阅话题' }}<AppIcon
                v-if="detail.subscribed"
                name="check"
                class="action-check"
              />
            </button><p
              v-if="actionErrors.subscription"
              class="form-error"
              role="alert"
            >
              {{ actionErrors.subscription }}
            </p><button
              v-if="detail.canEdit"
              :disabled="busy"
              @click="beginEdit"
            >
              <AppIcon name="settings" />编辑话题
            </button><button
              v-if="detail.canEdit"
              class="danger-action"
              :disabled="busy"
              @click="deleting = 'topic'"
            >
              <AppIcon name="close" />删除话题
            </button>
          </div>
        </section>
        <section
          v-else
          id="topic-timeline"
          role="tabpanel"
          aria-labelledby="timeline-tab"
          class="sidebar-timeline"
        >
          <h2>处理记录</h2><ol>
            <li
              v-for="event in detail.events"
              :key="event.id"
            >
              <span class="timeline-dot" /><strong>{{ eventNames[event.type] || event.type }}</strong><time>{{ formatDate(event.createdAt) }}</time><p v-if="event.reason">
                {{ event.reason }}
              </p>
            </li>
          </ol>
        </section>
      </aside>
    </div>

    <AppDialog
      v-if="composing || editing"
      :title="editing ? '编辑话题' : '新建话题'"
      :busy="busy"
      @close="clearForms"
    >
      <form
        id="topic-form"
        class="topic-form"
        @submit.prevent="submitTopic"
      >
        <label for="issue-title">话题标题</label><input
          id="issue-title"
          v-model="title"
          placeholder="简要描述你想讨论的问题"
          maxlength="150"
          required
          :disabled="busy"
        ><label for="issue-body">话题正文</label><textarea
          id="issue-body"
          v-model="body"
          placeholder="补充具体情况…"
          rows="8"
          maxlength="20000"
          required
          :disabled="busy"
        /><p
          v-if="actionErrors.topic"
          role="alert"
          class="form-error"
        >
          {{ actionErrors.topic }}
        </p>
      </form><template #footer>
        <button
          class="quiet-button"
          :disabled="busy"
          @click="clearForms"
        >
          取消
        </button><button
          form="topic-form"
          class="primary-button"
          :disabled="busy || !title.trim() || !body.trim()"
        >
          {{ busy ? '保存中…' : '提交话题' }}
        </button>
      </template>
    </AppDialog>
    <AppDialog
      v-if="deleting"
      title="确认删除"
      :busy="busy"
      @close="deleting = null"
    >
      <p>确认删除{{ deleting === 'topic' ? '此话题' : '这条评论' }}？{{ deleting === 'topic' ? '已有讨论将保留。' : '其他人的回复会保留在原讨论中。' }}</p><p
        v-if="actionErrors.delete"
        role="alert"
        class="form-error"
      >
        {{ actionErrors.delete }}
      </p><template #footer>
        <button
          class="quiet-button"
          :disabled="busy"
          @click="deleting = null"
        >
          取消
        </button><button
          class="primary-button danger"
          :disabled="busy"
          @click="remove"
        >
          确认删除
        </button>
      </template>
    </AppDialog>
  </section>
</template>

<style scoped>
.discussion-page { max-width: 1280px; margin: 0 auto; padding: 30px 36px 64px; --discussion-soft: var(--green-soft, #eef5f0); --discussion-danger: #a54e46; }
.discussion-breadcrumb { display: flex; align-items: center; gap: 12px; min-height: 32px; color: var(--muted); font-size: 13px; margin-bottom: 28px; }
.discussion-breadcrumb a { display: inline-flex; align-items: center; gap: 8px; min-height: 36px; }.discussion-breadcrumb a:first-child { max-width: 65%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.discussion-breadcrumb .app-icon { width: 15px; flex-shrink: 0; }
.discussion-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 28px; }.discussion-heading h1 { margin: 0; font-size: 28px; line-height: 1.5; font-weight: 650; letter-spacing: -.5px; overflow-wrap: anywhere; }.discussion-heading > div { min-width: 0; }
.new-topic-button { flex-shrink: 0; }.new-topic-button > span { font-size: 22px; font-weight: 400; line-height: 1; }
.topic-heading-meta { display: flex; align-items: center; gap: 14px; color: var(--muted); font-size: 13px; margin-top: 14px; }.back-to-topics { display: inline-flex; gap: 8px; align-items: center; flex-shrink: 0; min-height: 44px; color: var(--muted); font-size: 13px; }.back-to-topics .app-icon { width: 17px; }
.topic-board { background: var(--paper); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }.topic-toolbar { min-height: 76px; display: flex; justify-content: space-between; align-items: center; gap: 24px; padding: 12px 24px; background: var(--discussion-soft); border-bottom: 1px solid var(--line); }
.topic-statistics { display: flex; align-items: center; gap: 22px; }.topic-statistics button { display: inline-flex; align-items: center; gap: 7px; min-height: 44px; padding: 0; border: 0; background: transparent; color: var(--muted); font-size: 14px; cursor: pointer; }.topic-statistics button.active { color: var(--ink); }.topic-statistics strong { font-weight: 650; }.topic-statistics .app-icon { width: 18px; }
.topic-filters { display: flex; align-items: center; gap: 18px; }.topic-filters label { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }.topic-filters .app-icon { width: 16px; }.topic-filters select { max-width: 130px; min-height: 44px; border: 0; background: transparent; color: var(--ink); font: inherit; cursor: pointer; }
.topic-row { display: flex; gap: 18px; align-items: flex-start; padding: 25px 26px; border-bottom: 1px solid var(--line); transition: background 160ms ease; }.topic-row:last-of-type { border-bottom: 0; }.topic-row:hover { background: var(--discussion-soft); }.topic-state-icon { display: inline-flex; color: var(--green); margin-top: 3px; flex-shrink: 0; }.topic-state-icon .app-icon { width: 21px; height: 21px; }.topic-state-icon[data-status=closed] { color: var(--muted); }.topic-row-content { flex: 1; min-width: 0; }.topic-title { font-size: 17px; font-weight: 600; line-height: 1.65; overflow-wrap: anywhere; }.topic-title:hover { color: var(--green); }.topic-row-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--muted); margin-top: 10px; }.topic-row-meta > a { display: inline-flex; align-items: center; gap: 6px; }.topic-row-meta :deep(.user-avatar) { width: 20px; height: 20px; flex-shrink: 0; }.topic-row-end { display: flex; align-items: center; gap: 22px; padding-top: 3px; flex-shrink: 0; }.topic-reply-count { display: flex; align-items: center; gap: 7px; min-height: 30px; min-width: 38px; font-size: 13px; color: var(--muted); }.topic-reply-count svg { width: 16px; height: 16px; stroke: currentColor; stroke-width: 1.5; }
.issue-status { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 500; line-height: 1; min-height: 27px; padding: 6px 10px; border: 1px solid var(--line); border-radius: 6px; color: var(--muted); background: var(--paper); white-space: nowrap; }.issue-status i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }.issue-status[data-status=open] { color: #8a642c; background: #fcf7ec; border-color: #eee4cb; }.issue-status[data-status=resolved] { color: var(--green); background: var(--discussion-soft); border-color: #d6e5dc; }
.topic-empty { padding: 70px 24px; text-align: center; }.topic-empty > .app-icon { width: 36px; height: 36px; color: var(--muted); }.topic-empty h2 { font-size: 16px; font-weight: 500; margin: 18px 0 10px; }
.topic-detail-layout { display: grid; grid-template-columns: minmax(0, 1fr) 250px; gap: 24px; align-items: start; }.topic-main { background: var(--paper); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; min-width: 0; }.topic-author-bar { min-height: 80px; padding: 18px 28px; display: flex; align-items: center; gap: 12px; background: var(--discussion-soft); border-bottom: 1px solid var(--line); font-size: 14px; }.topic-author { display: flex; align-items: center; gap: 12px; min-width: 0; }.topic-author strong { overflow-wrap: anywhere; font-weight: 600; }.topic-author :deep(.user-avatar) { width: 36px; height: 36px; flex-shrink: 0; }.topic-author-bar time { margin-left: auto; font-size: 12px; color: var(--muted); white-space: nowrap; }.author-role-label { font-size: 11px; color: var(--green); border: 1px solid #d1dfd6; border-radius: 4px; padding: 2px 6px; white-space: nowrap; }.topic-content { padding: 34px 30px 42px; margin: 0; min-height: 190px; font-size: 15px; }
.topic-comments-block { border-top: 1px solid var(--line); padding: 26px 30px 10px; }.comments-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 25px; }.comments-heading h2 { font-size: 18px; margin: 0; }.comments-heading h2 span { margin-left: 8px; font-size: 14px; font-weight: 400; color: var(--muted); }.comments-heading > span { font-size: 12px; color: var(--muted); }.comment-composer { display: flex; align-items: flex-start; gap: 14px; margin: 20px 0 26px; }.comment-composer > :deep(.user-avatar) { width: 38px; height: 38px; flex-shrink: 0; }.composer-content { flex: 1; min-width: 0; }.composer-content textarea { width: 100%; min-height: 90px; border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: var(--page-background); color: var(--ink); font: inherit; font-size: 14px; line-height: 1.7; resize: vertical; transition: border-color 160ms; }.composer-content textarea:focus { outline: 2px solid var(--green-soft); border-color: var(--green); background: var(--paper); }.composer-footer { display: flex; justify-content: flex-end; align-items: center; gap: 12px; margin-top: 10px; }.composer-footer .primary-button { min-height: 38px; padding: 8px 22px; font-size: 13px; }.inline-composer { margin-left: 54px; }.inline-composer label { display: block; font-size: 13px; margin-bottom: 10px; color: var(--green); }
.comment-thread { padding: 23px 0 10px; border-top: 1px solid var(--line); }.comment-entry { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 18px; scroll-margin-top: 140px; border-radius: 6px; }.comment-entry:target { background: var(--discussion-soft); outline: 6px solid var(--discussion-soft); }.comment-avatar { flex-shrink: 0; }.comment-avatar :deep(.user-avatar) { width: 38px; height: 38px; }.comment-copy { flex: 1; min-width: 0; padding-top: 2px; }.comment-byline { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 13px; color: var(--muted); font-weight: 500; }.comment-byline a:hover { color: var(--green); }.comment-role { font-size: 10px; padding: 1px 4px; color: var(--green); background: var(--discussion-soft); border-radius: 3px; }.comment-text { font-size: 14px; margin: 8px 0 2px; line-height: 1.85; }.comment-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 18px; font-size: 12px; color: var(--muted); }.comment-meta button { min-height: 36px; padding: 0; background: none; border: none; font-size: 12px; color: var(--muted); cursor: pointer; }.comment-meta button:hover { color: var(--green); }.comment-meta .comment-delete:hover { color: var(--discussion-danger); }.child-reply { margin-left: 52px; gap: 11px; margin-bottom: 10px; }.child-reply .comment-avatar :deep(.user-avatar) { width: 27px; height: 27px; }.child-reply .comment-byline { font-size: 12px; }.child-reply .comment-text { margin-top: 4px; }.reply-target { margin: 5px 0 0; font-size: 12px; color: var(--muted); }.reply-target a { color: var(--green); }.thread-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 14px; margin: 0 0 12px 91px; font-size: 12px; color: var(--muted); }.thread-controls button { display: inline-flex; align-items: center; gap: 5px; min-height: 36px; padding: 0; background: none; border: none; color: var(--green); font: inherit; cursor: pointer; }.thread-controls .app-icon { width: 13px; }.discussion-closed { display: flex; gap: 10px; align-items: center; color: var(--muted); font-size: 13px; padding: 14px; background: var(--page-background); border-radius: 7px; }.discussion-closed .app-icon { width: 17px; }.comments-empty { text-align: center; padding: 32px 0; color: var(--muted); font-size: 14px; }
.topic-sidebar { position: sticky; top: 100px; border: 1px solid var(--line); border-radius: 12px; background: var(--paper); overflow: hidden; }.sidebar-tabs { display: flex; border-bottom: 1px solid var(--line); padding: 0 16px; gap: 24px; }.sidebar-tabs button { min-height: 54px; border: 0; background: none; padding: 0 4px; color: var(--muted); font: inherit; font-size: 13px; cursor: pointer; border-bottom: 2px solid transparent; }.sidebar-tabs button[aria-selected=true] { color: var(--green); border-bottom-color: var(--green); font-weight: 600; }.sidebar-section { padding: 20px; border-bottom: 1px solid var(--line); }.sidebar-section:last-child { border-bottom: 0; }.sidebar-section h2, .sidebar-timeline h2 { font-size: 12px; font-weight: 500; color: var(--muted); margin: 0 0 14px; }.state-form { display: grid; gap: 12px; }.state-form > label { font-size: 12px; color: var(--muted); }.state-form select, .state-form textarea { width: 100%; min-height: 42px; padding: 10px; border: 1px solid var(--line); border-radius: 6px; background: var(--paper); color: var(--ink); font: inherit; font-size: 13px; }.state-form textarea { resize: vertical; }.side-save { min-height: 38px; border: 1px solid var(--line); border-radius: 6px; background: var(--paper); color: var(--green); font: inherit; font-size: 12px; cursor: pointer; }.side-save:hover:not(:disabled) { background: var(--discussion-soft); border-color: var(--green); }.side-actions > button { display: flex; width: 100%; gap: 10px; align-items: center; min-height: 44px; margin: 3px 0; border: none; border-radius: 6px; padding: 9px 10px; background: transparent; color: var(--ink); font-size: 13px; text-align: left; cursor: pointer; }.side-actions > button:hover { background: var(--discussion-soft); }.side-actions .app-icon { width: 16px; height: 16px; color: var(--muted); }.side-actions .action-check { margin-left: auto; color: var(--green); }.side-actions .danger-action, .side-actions .danger-action .app-icon { color: var(--discussion-danger); }.sidebar-timeline { padding: 22px 20px; }.sidebar-timeline ol { padding: 0 0 0 9px; list-style: none; margin: 0; }.sidebar-timeline li { position: relative; padding: 0 0 26px 20px; border-left: 1px solid var(--line); font-size: 12px; }.sidebar-timeline li:last-child { padding-bottom: 0; border-left-color: transparent; }.timeline-dot { position: absolute; top: 3px; left: -4px; width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 4px var(--paper); }.sidebar-timeline strong { display: block; font-weight: 500; line-height: 1.5; }.sidebar-timeline time { display: block; margin-top: 7px; color: var(--muted); font-size: 11px; line-height: 1.6; }.sidebar-timeline p { margin: 10px 0 0; color: var(--muted); line-height: 1.8; overflow-wrap: anywhere; white-space: pre-wrap; }
.discussion-pagination { display: flex; align-items: center; justify-content: center; gap: 20px; padding: 22px; font-size: 13px; color: var(--muted); border-top: 1px solid var(--line); }.discussion-pagination button { min-height: 40px; border: 1px solid var(--line); border-radius: 6px; padding: 8px 14px; background: var(--paper); font: inherit; color: var(--ink); cursor: pointer; }.topic-form { display: grid; gap: 12px; }.topic-form label { font-size: 13px; font-weight: 500; }.topic-form input, .topic-form textarea { width: 100%; font: inherit; font-size: 14px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 7px; background: var(--paper); color: var(--ink); }.topic-form textarea { line-height: 1.8; resize: vertical; }.quiet-button { min-height: 40px; padding: 8px 16px; background: none; border: 1px solid var(--line); border-radius: 6px; color: var(--muted); cursor: pointer; font: inherit; font-size: 13px; }.discussion-error { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 14px 18px; margin-bottom: 20px; border: 1px solid #e9c9c2; border-radius: 8px; background: #fff7f5; color: var(--discussion-danger); font-size: 14px; }.discussion-loading { padding: 35px 0; color: var(--muted); text-align: center; }.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }.discussion-page button { touch-action: manipulation; }.discussion-page button:disabled { opacity: .45; cursor: not-allowed; }
@media(max-width:1000px) { .topic-detail-layout { grid-template-columns: minmax(0,1fr) 220px; gap: 18px; }.discussion-page { padding: 24px; }.topic-toolbar { gap: 12px; padding: 12px 18px; }.topic-filters { gap: 10px; }.topic-author-bar { flex-wrap: wrap; }.topic-author-bar time { margin-left: 0; }.topic-content, .topic-comments-block { padding-left: 24px; padding-right: 24px; } }
@media(max-width:760px) { .discussion-page { padding: 20px 16px 40px; }.discussion-breadcrumb { margin-bottom: 20px; font-size: 12px; gap: 8px; }.discussion-heading { gap: 14px; margin-bottom: 22px; }.discussion-heading h1 { font-size: 23px; }.new-topic-button { padding: 10px 14px; font-size: 13px; }.topic-toolbar { flex-wrap: wrap; gap: 6px; padding: 10px 16px; }.topic-statistics { gap: 24px; width: 100%; }.topic-filters { width: 100%; justify-content: space-between; border-top: 1px solid var(--line); gap: 8px; }.topic-row { padding: 20px 16px; gap: 10px; }.topic-title { font-size: 15px; }.topic-row-end { flex-direction: column; align-items: flex-end; gap: 10px; }.topic-row-meta { gap: 8px; }.topic-row-meta time { width: 100%; }.topic-state-icon .app-icon { width: 18px; }.topic-detail-layout { display: flex; flex-direction: column; gap: 18px; }.topic-main, .topic-sidebar { width: 100%; }.topic-sidebar { position: static; }.topic-author-bar { padding: 16px 18px; gap: 10px; }.topic-author-bar time { width: 100%; padding-left: 46px; }.topic-author strong { font-size: 13px; }.topic-content { min-height: 150px; padding: 24px 18px 30px; font-size: 15px; }.topic-comments-block { padding: 22px 18px 4px; }.comment-avatar :deep(.user-avatar), .comment-composer > :deep(.user-avatar) { width: 32px; height: 32px; }.comment-entry, .comment-composer { gap: 10px; }.child-reply { margin-left: 22px; }.child-reply .comment-avatar :deep(.user-avatar) { width: 24px; height: 24px; }.comment-byline { overflow-wrap: anywhere; }.comment-meta { column-gap: 14px; row-gap: 0; }.comment-meta time { width: 100%; }.thread-controls { margin-left: 56px; gap: 12px; }.inline-composer { margin-left: 22px; }.back-to-topics { font-size: 12px; }.composer-content textarea { font-size: 16px; }.sidebar-tabs { gap: 30px; }.side-actions { display: flex; flex-wrap: wrap; gap: 6px; }.side-actions h2 { width: 100%; }.side-actions > button { width: auto; }.sidebar-section { padding: 18px; }.sidebar-section.state-form { grid-template-columns: 1fr 1fr; }.state-form > label, .state-form > textarea, .state-form .state-reason-label { grid-column: 1 / -1; }.state-form > select { min-width: 0; }.sidebar-timeline li { padding-bottom: 20px; }.comment-meta button { min-height: 44px; } }
@media(prefers-reduced-motion:reduce) { .topic-row, .composer-content textarea { transition: none; } }
.topic-heading-actions{display:flex;align-items:center;justify-content:flex-end;gap:14px;flex-shrink:0}.comment-meta :deep(.report-menu-trigger){width:32px;height:32px;min-height:32px;border-color:transparent;background:transparent}.comment-meta :deep(.report-menu-trigger:hover){background:var(--green-soft)}
@media(max-width:760px){.topic-heading-actions{gap:12px}.comment-meta :deep(.report-menu-trigger){width:44px;height:44px;min-height:44px}}
/* 举报菜单需越过讨论卡片边界；顶部背景单独保留圆角。 */
.topic-main{overflow:visible}.topic-author-bar{border-radius:13px 13px 0 0}
</style>
