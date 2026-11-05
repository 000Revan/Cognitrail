<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { deleteNotification, deleteNotificationHistory, notifications, notificationLabel, notificationTarget, readNotification, readThrough, unreadCount } from '../../api/notification'
import type { Notification } from '../../api/notification'
import { useAuthStore } from '../../stores/auth'
import { formatDate } from '../../domain/roadmap'

import AppIcon from '../../components/common/AppIcon.vue'
import AppDialog from '../../components/common/AppDialog.vue'

const auth = useAuthStore(), router = useRouter()
const rows = ref<Notification[]>([]), page = ref(1), total = ref(0), count = ref(0), unread = ref(false)
const loading = ref(false), busy = ref(false), error = ref('')
const itemNotices = ref<Record<string, string>>({}), toolbarError = ref('')
const openingId = ref<string | null>(null)
type DeleteIntent = { kind: 'one'; id: string } | { kind: 'read' | 'all'; throughId: string }
const deletion = ref<DeleteIntent | null>(null), deleteError = ref(''), cleanupOpen = ref(false), latestId = ref<string | null>(null)
const deletionTitle = computed(() => deletion.value?.kind === 'one' ? '删除消息' : deletion.value?.kind === 'read' ? '清理已读消息' : '清空历史消息')
const pages = computed(() => Math.max(1, Math.ceil(total.value / 20)))
const kinds: Record<string, { label: string; icon: string }> = {
  issue_created: { label: '新话题', icon: 'message' },
  comment_created: { label: '讨论回复', icon: 'message' },
  issue_state_changed: { label: '处理进展', icon: 'check' },
  release_published: { label: '路线更新', icon: 'repository' },
}
function kind(type: string) { return kinds[type] || { label: '站内通知', icon: 'bell' } }
function filterUnread(value: boolean) {
  if (loading.value || busy.value || unread.value === value) return
  unread.value = value; page.value = 1; void load()
}
let generation = 0
async function load(reset = false) {
  const ticket = ++generation
  if (reset) { rows.value = []; count.value = total.value = 0; page.value = 1; busy.value = false; openingId.value = null }
  if (reset) { deletion.value = null; deleteError.value = ''; latestId.value = null; cleanupOpen.value = false }
  itemNotices.value = {}; toolbarError.value = ''
  loading.value = true; error.value = ''
  try {
    const [result, unseen] = await Promise.all([notifications(page.value, unread.value), unreadCount()])
    if (ticket !== generation) return
    rows.value = result.items; total.value = result.total; count.value = unseen; page.value = result.page
    latestId.value = result.latestId || null
  } catch (cause) { if (ticket === generation) error.value = cause instanceof Error ? cause.message : '消息加载失败' }
  finally { if (ticket === generation) loading.value = false }
}
watch([() => auth.user?.id, () => auth.sessionVersion], () => void load(true), { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++; window.removeEventListener('pointerdown', outsideCleanup) })
onMounted(() => window.addEventListener('pointerdown', outsideCleanup))
function outsideCleanup(event: PointerEvent) { if (!(event.target as Element).closest('.message-cleanup')) cleanupOpen.value = false }
async function closeCleanup() { cleanupOpen.value = false; await nextTick(); document.getElementById('message-cleanup-toggle')?.focus() }
function requestDelete(item: Notification) { deleteError.value = ''; deletion.value = { kind: 'one', id: item.id } }
function requestCleanup(kind: 'read' | 'all') {
  if (!latestId.value) return
  deleteError.value = ''; cleanupOpen.value = false; deletion.value = { kind, throughId: latestId.value }
}
async function confirmDelete() {
  const intent = deletion.value
  if (!intent || busy.value) return
  const ticket = generation; busy.value = true; deleteError.value = ''
  try {
    if (intent.kind === 'one') await deleteNotification(intent.id)
    else await deleteNotificationHistory(intent.throughId, intent.kind === 'read')
    if (ticket !== generation) return
    window.dispatchEvent(new Event('cognitrail:notifications-changed'))
    deletion.value = null; busy.value = false
    await load()
    if (generation === ticket + 1) { await nextTick(); document.querySelector<HTMLButtonElement>('.message-filters button')?.focus() }
  } catch (cause) { if (ticket === generation) deleteError.value = cause instanceof Error ? cause.message : '删除失败，请重试' }
  finally { if (ticket === generation) busy.value = false }
}
async function act(work: () => Promise<void>, itemId?: string) {
  if (busy.value) return
  const ticket = generation; busy.value = true
  if (itemId) itemNotices.value[itemId] = ''
  else toolbarError.value = ''
  try { await work() } catch (cause) {
    if (ticket === generation) {
      const message = cause instanceof Error ? cause.message : '操作失败，请重试'
      if (itemId) itemNotices.value[itemId] = message
      else toolbarError.value = message
    }
  }
  finally { if (ticket === generation) busy.value = false }
}
async function open(item: Notification) {
  if (busy.value || loading.value) return
  const ticket = generation
  openingId.value = item.id
  await act(async () => {
    const target = await notificationTarget(item.id)
    if (ticket !== generation) return
    await readNotification(item.id)
    if (ticket !== generation) return
    window.dispatchEvent(new Event('cognitrail:notifications-changed'))
    if (target.accessible && target.path) await router.push(target.path)
    else {
      if (!item.readAt) { item.readAt = new Date().toISOString(); count.value = Math.max(0, count.value - 1) }
      itemNotices.value[item.id] = target.message || '目标内容不可访问'
    }
  }, item.id)
  if (ticket === generation) openingId.value = null
}
async function markAll() {
  const newest = rows.value[0]?.id
  if (!newest) return
  const ticket = generation
  await act(async () => {
    await readThrough(newest)
    if (ticket === generation) { window.dispatchEvent(new Event('cognitrail:notifications-changed')); busy.value = false; await load() }
  })
}
</script>

<template>
  <section
    class="content-page messages-page"
    :aria-busy="loading || busy"
  >
    <header class="messages-heading">
      <div class="messages-title">
        <span class="messages-symbol"><AppIcon name="bell" /></span>
        <div>
          <h1>站内消息</h1><p aria-live="polite">
            {{ count }} 条未读
          </p>
        </div>
      </div>
    </header>

    <div class="message-board">
      <div class="message-toolbar">
        <div
          class="message-filters"
          role="group"
          aria-label="消息筛选"
        >
          <button
            type="button"
            :aria-pressed="!unread"
            aria-label="全部消息"
            :disabled="loading || busy"
            @click="filterUnread(false)"
          >
            全部消息
          </button>
          <button
            type="button"
            :aria-pressed="unread"
            aria-label="仅看未读"
            :disabled="loading || busy"
            @click="filterUnread(true)"
          >
            仅看未读<span
              v-if="count"
              class="unread-count"
            >{{ count > 99 ? '99+' : count }}</span>
          </button>
        </div>
        <div class="message-tools">
          <button
            type="button"
            class="refresh-messages"
            aria-label="刷新消息"
            title="刷新消息"
            :disabled="loading || busy"
            @click="load()"
          >
            <AppIcon name="refresh" /><span>刷新</span>
          </button>
          <button
            type="button"
            aria-label="将当前列表及更早消息标为已读"
            title="将当前列表及更早消息标为已读"
            :disabled="loading || busy || !rows.length || !count"
            @click="markAll"
          >
            <AppIcon name="check" /><span class="tool-label">批量已读</span>
          </button>
          <div
            class="message-cleanup"
            @keydown.esc.stop.prevent="closeCleanup"
          >
            <button
              id="message-cleanup-toggle"
              type="button"
              aria-label="清理消息"
              title="清理消息"
              :aria-expanded="cleanupOpen"
              aria-controls="message-cleanup-options"
              :disabled="loading || busy || !latestId"
              @click="cleanupOpen = !cleanupOpen"
            >
              <AppIcon name="trash" /><span class="tool-label">清理消息</span>
            </button>
            <div
              v-if="cleanupOpen"
              id="message-cleanup-options"
              class="cleanup-options"
              role="group"
              aria-label="历史消息清理"
            >
              <button
                type="button"
                @click="requestCleanup('read')"
              >
                清理已读消息
              </button>
              <button
                type="button"
                @click="requestCleanup('all')"
              >
                清空历史消息
              </button>
            </div>
          </div>
        </div>
        <p
          v-if="toolbarError"
          class="form-error toolbar-error"
          role="alert"
        >
          {{ toolbarError }}
        </p>
      </div>

      <div
        v-if="loading"
        class="message-loading"
        role="status"
      >
        <p class="messages-sr-only">
          正在加载消息…
        </p>
        <div
          v-for="index in 3"
          :key="index"
          class="message-skeleton"
          aria-hidden="true"
        >
          <i /><div><span /><span /></div>
        </div>
      </div>
      <div
        v-else-if="error"
        class="message-state message-load-error"
        role="alert"
      >
        <span class="empty-symbol"><AppIcon name="refresh" /></span>
        <h2>消息加载失败</h2><p>{{ error }}</p>
        <button
          type="button"
          class="outline-link"
          @click="load()"
        >
          重新加载
        </button>
      </div>
      <div
        v-else-if="!rows.length"
        class="message-state"
      >
        <span class="empty-symbol"><AppIcon :name="unread ? 'check' : 'message'" /></span>
        <h2>{{ unread ? '没有未读消息' : '暂时没有消息' }}</h2>
        <button
          v-if="unread"
          type="button"
          class="outline-link"
          @click="filterUnread(false)"
        >
          查看全部消息
        </button>
        <RouterLink
          v-else
          class="outline-link"
          to="/"
        >浏览社区</RouterLink>
      </div>
      <div
        v-else
        class="message-list"
      >
        <article
          v-for="item in rows"
          :key="item.id"
          class="message-card"
          :class="{ 'is-unread': !item.readAt }"
          :data-type="item.type"
          :data-notification-id="item.id"
        >
          <button
            type="button"
            class="message-open"
            aria-label="查看消息"
            :aria-describedby="'message-title-' + item.id"
            :disabled="busy || loading"
            @click="open(item)"
          >
            <span class="message-type-icon"><AppIcon :name="kind(item.type).icon" /></span>
            <span class="message-copy">
              <span class="message-byline"><span class="message-category">{{ kind(item.type).label }}</span><span
                class="message-read-state"
                :class="{ unread: !item.readAt }"
              ><i v-if="!item.readAt" />{{ item.readAt ? '已读' : '未读' }}</span></span>
              <strong :id="'message-title-' + item.id">{{ notificationLabel(item.type) }}</strong>
              <time :datetime="item.createdAt">{{ formatDate(item.createdAt) }}</time>
            </span>
            <span class="message-go"><span>{{ openingId === item.id ? '打开中…' : '查看消息' }}</span><AppIcon name="chevron" /></span>
          </button>
          <button
            type="button"
            class="delete-message"
            aria-label="删除消息"
            title="删除消息"
            :disabled="busy || loading"
            @click="requestDelete(item)"
          >
            <AppIcon name="trash" />
          </button>
          <p
            v-if="itemNotices[item.id]"
            class="form-error message-item-notice"
            role="alert"
          >
            <AppIcon name="shield" />{{ itemNotices[item.id] }}
          </p>
        </article>
      </div>

      <footer
        v-if="!loading && !error && total"
        class="messages-footer"
      >
        <span>共 {{ total }} 条{{ unread ? '未读消息' : '消息' }}</span>
        <nav
          v-if="total > 20"
          class="message-pagination"
          aria-label="消息分页"
        >
          <button
            type="button"
            :disabled="page <= 1 || busy"
            @click="page--; load()"
          >
            上一页
          </button><span>{{ page }} / {{ pages }}</span><button
            type="button"
            :disabled="page * 20 >= total || busy"
            @click="page++; load()"
          >
            下一页
          </button>
        </nav>
      </footer>
    </div>
    <AppDialog
      v-if="deletion"
      :title="deletionTitle"
      :busy="busy"
      @close="deletion = null"
    >
      <p
        v-if="deletion.kind === 'one'"
        class="delete-description"
      >
        这条消息将从你的收件箱移除，不影响原话题和评论。删除后无法恢复。
      </p>
      <p
        v-else-if="deletion.kind === 'read'"
        class="delete-description"
      >
        移除已收到的已读消息，保留未读消息和之后收到的新消息。删除后无法恢复。
      </p>
      <p
        v-else
        class="delete-description"
      >
        移除已收到的全部历史消息，包括未读消息。之后收到的新消息会保留，删除后无法恢复。
      </p>
      <p
        v-if="deleteError"
        class="form-error"
        role="alert"
      >
        {{ deleteError }}
      </p>
      <template #footer>
        <button
          type="button"
          class="outline-link"
          :disabled="busy"
          @click="deletion = null"
        >
          取消
        </button>
        <button
          type="button"
          class="primary-button delete-confirm"
          :disabled="busy"
          @click="confirmDelete"
        >
          {{ busy ? '删除中…' : '确认删除' }}
        </button>
      </template>
    </AppDialog>
  </section>
</template>

<style scoped>
.messages-page { max-width: 1040px; margin: auto; padding: 40px 36px 64px; }
.messages-heading { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 28px; }
.messages-title { display: flex; align-items: center; gap: 15px; }
.messages-symbol { display: grid; place-items: center; width: 48px; height: 48px; background: var(--green-soft); color: var(--green); border-radius: 12px; }
.messages-symbol .app-icon { width: 25px; height: 25px; }
.messages-heading h1 { margin: 0; font-size: 30px; line-height: 1.4; font-weight: 600; letter-spacing: -.5px; }
.messages-heading p { margin: 5px 0 0; color: var(--muted); font-size: 13px; }
.message-board { border: 1px solid var(--line); border-radius: 14px; background: var(--paper); }
.message-cleanup { position: relative; }
.cleanup-options { position: absolute; right: 0; top: calc(100% + 5px); z-index: 5; min-width: 160px; padding: 6px; background: var(--paper); border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 8px 24px #173d2d1a; }
.message-tools .cleanup-options button { display: flex; width: 100%; justify-content: flex-start; padding: 10px 12px; }
.message-tools .cleanup-options button:last-child { color: #ad3939; }
.delete-description { margin: 0; color: var(--muted); line-height: 1.8; }
.delete-confirm { background: #ad3939; border-color: #ad3939; color: white; }
.message-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 20px; padding: 12px 22px 0; border-bottom: 1px solid var(--line); }
.message-filters { display: flex; gap: 24px; }
.message-filters button { position: relative; display: inline-flex; align-items: center; gap: 8px; min-height: 52px; padding: 0 2px 12px; background: transparent; border: 0; color: var(--muted); font: inherit; font-size: 14px; cursor: pointer; }
.message-filters button[aria-pressed=true] { color: var(--green); font-weight: 600; }
.message-filters button[aria-pressed=true]::after { position: absolute; bottom: -1px; left: 0; right: 0; height: 3px; content: ''; border-radius: 3px 3px 0 0; background: var(--green); }
.unread-count { padding: 2px 6px; min-width: 22px; border-radius: 5px; font-size: 11px; line-height: 1.4; background: var(--green-soft); color: var(--green); }
.message-tools { display: flex; align-items: center; gap: 14px; padding-bottom: 10px; }
.message-tools button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 40px; padding: 7px 4px; border: 0; border-radius: 5px; background: transparent; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; }
.message-tools .app-icon { width: 15px; height: 15px; }
.message-tools button:hover:not(:disabled) { color: var(--green); background: var(--green-soft); }
.toolbar-error { flex-basis: 100%; margin: 0 0 12px; font-size: 13px; }
.message-card { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) 52px; background: var(--paper); border-bottom: 1px solid var(--line); }
.delete-message { align-self: center; justify-self: start; display: grid; place-items: center; width: 36px; height: 36px; padding: 0; border: 0; border-radius: 7px; background: transparent; color: var(--muted); cursor: pointer; }
.delete-message:hover:not(:disabled) { color: #ad3939; background: #fff0f0; }
.delete-message .app-icon { width: 17px; height: 17px; }
.message-card:last-child { border-bottom: 0; }
.message-card.is-unread { background: var(--message-unread, #f3f9f6); }
.message-card.is-unread::before { position: absolute; content: ''; top: 25px; bottom: 25px; left: 0; width: 3px; background: var(--green); border-radius: 0 3px 3px 0; pointer-events: none; }
.message-open { display: grid; grid-template-columns: 42px minmax(0, 1fr) auto; align-items: start; gap: 18px; width: 100%; padding: 24px 28px; border: 0; background: transparent; text-align: left; color: var(--ink); font: inherit; cursor: pointer; }
.message-open:hover:not(:disabled) { background: var(--green-soft); }
.message-type-icon { display: grid; place-items: center; width: 42px; height: 42px; color: var(--muted); background: var(--surface-soft, #f4f6f5); border: 1px solid var(--line); border-radius: 11px; }
.is-unread .message-type-icon { color: var(--green); background: var(--paper); border-color: transparent; }
.message-type-icon .app-icon { width: 21px; height: 21px; }
.message-copy { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; min-width: 0; }
.message-byline { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; line-height: 1.4; }
.message-category { font-size: 11px; color: var(--muted); }
.message-read-state { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--muted); }
.message-read-state.unread { color: var(--green); }
.message-read-state i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.message-copy strong { font-size: 15px; line-height: 1.6; font-weight: 500; overflow-wrap: anywhere; }
.is-unread .message-copy strong { font-weight: 600; }
.message-copy time { color: var(--muted); font-size: 12px; line-height: 1.5; }
.message-go { display: flex; align-items: center; gap: 8px; align-self: center; color: var(--green); font-size: 12px; white-space: nowrap; }
.message-go .app-icon { width: 15px; height: 15px; transform: rotate(-90deg); }
.message-item-notice { grid-column: 1 / -1; display: flex; align-items: flex-start; gap: 8px; margin: 0 28px 20px 88px; font-size: 13px; line-height: 1.7; }
.message-item-notice .app-icon { width: 16px; height: 16px; flex-shrink: 0; margin-top: 3px; }
.messages-footer { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; padding: 18px 28px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }
.message-pagination { display: flex; align-items: center; gap: 14px; }
.message-pagination button { min-height: 36px; padding: 6px 10px; border: 1px solid var(--line); border-radius: 5px; background: var(--paper); color: var(--ink); font: inherit; cursor: pointer; }
.message-state { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 330px; padding: 44px 24px; text-align: center; }
.empty-symbol { display: grid; place-items: center; width: 64px; height: 64px; margin-bottom: 20px; border-radius: 18px; background: var(--green-soft); color: var(--green); }
.empty-symbol .app-icon { width: 30px; height: 30px; }
.message-state h2 { margin: 0 0 20px; font-size: 18px; font-weight: 500; }
.message-state p { max-width: 440px; margin: -8px 0 20px; font-size: 13px; color: var(--muted); line-height: 1.8; overflow-wrap: anywhere; }
.message-state .outline-link { min-height: 40px; font-size: 13px; padding: 8px 16px; }
.messages-page button:disabled { opacity: .45; cursor: not-allowed; }
.messages-page button:focus-visible, .messages-page a:focus-visible { outline: 2px solid var(--green); outline-offset: -3px; }
.message-loading { padding: 4px 28px; }
.message-skeleton { display: flex; gap: 18px; padding: 24px 0; }
.message-skeleton > i { width: 42px; height: 42px; border-radius: 11px; background: var(--surface-soft, #f1f5f2); flex-shrink: 0; }
.message-skeleton > div { display: flex; flex-direction: column; gap: 12px; flex: 1; padding-top: 6px; }
.message-skeleton span { display: block; width: min(65%, 340px); height: 14px; border-radius: 4px; background: var(--surface-soft, #f1f5f2); }
.message-skeleton span:last-child { width: min(40%, 180px); height: 10px; }
.messages-sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
@media (max-width: 650px) {
  .messages-page { padding: 28px 20px 44px; }
  .messages-heading { margin-bottom: 22px; }
  .messages-heading h1 { font-size: 26px; }
  .messages-symbol { width: 44px; height: 44px; border-radius: 10px; }
  .message-toolbar { padding: 8px 16px 0; gap: 0 12px; }
  .message-filters { gap: 20px; }
  .message-filters button { min-height: 48px; font-size: 13px; }
  .message-tools { gap: 2px; padding-bottom: 8px; }
  .message-tools .tool-label { display: none; }
  .message-tools > button, .message-cleanup > button { min-width: 36px; }
  .message-card { grid-template-columns: minmax(0, 1fr) 40px; }
  .delete-message { width: 32px; height: 36px; }
  .refresh-messages span { display: none; }
  .message-tools .refresh-messages { min-width: 36px; }
  .message-tools button { min-height: 36px; font-size: 11px; }
  .message-open { grid-template-columns: 36px minmax(0, 1fr) 15px; gap: 12px; padding: 22px 18px; }
  .message-type-icon { width: 36px; height: 36px; border-radius: 9px; }
  .message-type-icon .app-icon { width: 19px; height: 19px; }
  .message-copy strong { font-size: 14px; }
  .message-go > span { display: none; }
  .message-item-notice { margin: 0 18px 18px 66px; font-size: 12px; }
  .messages-footer { padding: 16px 18px; }
  .message-pagination { width: 100%; justify-content: center; }
}
</style>
