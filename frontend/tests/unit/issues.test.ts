import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IssuesView from '../../src/views/roadmap/IssuesView.vue'
import NotificationsView from '../../src/views/personal/NotificationsView.vue'
import { getIssue, issueAction, listIssues } from '../../src/api/issue'
import type { IssueDetail } from '../../src/api/issue'
import { deleteNotification, deleteNotificationHistory, notifications, notificationTarget, readNotification, readThrough, unreadCount } from '../../src/api/notification'
import { useAuthStore } from '../../src/stores/auth'

vi.mock('../../src/api/issue', () => ({ getIssue: vi.fn(), getReplies: vi.fn(), issueAction: vi.fn(), listIssues: vi.fn(), createIssue: vi.fn() }))
vi.mock('../../src/api/notification', () => ({ deleteNotification: vi.fn(), deleteNotificationHistory: vi.fn(), notifications: vi.fn(), notificationTarget: vi.fn(), readNotification: vi.fn(), readThrough: vi.fn(), unreadCount: vi.fn(), notificationLabel: () => '话题新回复' }))
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
function topic(status: 'open' | 'resolved' | 'closed' = 'open'): IssueDetail {
  return { id: '2', roadmapId: '1', title: '资源反馈', body: '问题正文', status, visibility: 'public',
    author: { id: '100', nickname: '提问者' }, createdAt: '2026-11-03T00:00:00Z', updatedAt: '2026-11-03T00:00:00Z', lastActivityAt: '2026-11-03T00:00:00Z',
    canEdit: false, canResolve: false, canClose: false, subscribed: false,
    comments: { items: [], total: 0, page: 1, pageSize: 20 }, events: [] }
}
beforeEach(() => {
  vi.resetAllMocks(); setActivePinia(createPinia())
  HTMLDialogElement.prototype.showModal = vi.fn()
  HTMLDialogElement.prototype.close = vi.fn()
})
async function setup(path: string, messages = false) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { template: '<p>社区发现</p>' } },
    { path: '/roadmaps/:id/issues', component: IssuesView },
    { path: '/roadmaps/:id/issues/:issueId', component: IssuesView },
    { path: '/roadmaps/:id', component: { template: '<p>路线</p>' } },
    { path: '/notifications', component: NotificationsView },
    { path: '/users/:userId', component: { template: '<p>用户主页</p>' } },
  ] })
  await router.push(path); await router.isReady()
  return { wrapper: mount(messages ? NotificationsView : IssuesView, { global: { plugins: [router] } }), router }
}

describe('R07私人响应与状态边界', () => {
  it('本人话题、根回复和子回复不提供举报入口，其他作者仍可举报', async () => {
    useAuthStore().user = { id: '100', username: 'owner', nickname: '本人', role: 'user', status: 'active', createdAt: '' }
    const detail = topic()
    const comment = { id: '10', body: '本人根回复', replyToCommentId: null, visibility: 'public', author: detail.author, canEdit: true, createdAt: detail.createdAt, updatedAt: detail.updatedAt }
    detail.comments = { items: [{ ...comment, replies: { items: [{ ...comment, id: '11', body: '本人子回复', replyToCommentId: '10' }, { ...comment, id: '12', body: '其他成员子回复', author: { id: '200', nickname: '其他成员' }, canEdit: false, replyToCommentId: '10' }], total: 2, page: 1, pageSize: 5 } }], total: 1, page: 1, pageSize: 20 }
    vi.mocked(getIssue).mockResolvedValue(detail)
    const { wrapper } = await setup('/roadmaps/1/issues/2'); await flushPromises()
    expect(wrapper.find('[aria-label="话题更多操作"]').exists()).toBe(false)
    expect(wrapper.findAll('[aria-label="回复更多操作"]')).toHaveLength(1)
    expect(wrapper.findAll('.comment-entry').filter(row => row.text().includes('本人根回复') || row.text().includes('本人子回复')).every(row => !row.find('[aria-haspopup="menu"]').exists())).toBe(true)
    wrapper.unmount()
  })

  const notice = { id: '9', type: 'comment_created', readAt: null, createdAt: '2026-11-03T00:00:00Z' }
  const inbox = { items: [notice], total: 1, page: 1, pageSize: 20, latestId: '12' }
  it('删除先确认，取消不写入；确认后刷新收件箱且无需访问原评论', async () => {
    vi.mocked(notifications).mockResolvedValueOnce(inbox).mockResolvedValue({ ...inbox, items: [], total: 0, latestId: null })
    vi.mocked(unreadCount).mockResolvedValueOnce(1).mockResolvedValue(0)
    vi.mocked(deleteNotification).mockResolvedValue({ deletedCount: 1 })
    const { wrapper } = await setup('/notifications', true); await flushPromises()
    await wrapper.get('[aria-label="删除消息"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text() === '取消')!.trigger('click')
    expect(deleteNotification).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="删除消息"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text() === '确认删除')!.trigger('click'); await flushPromises()
    expect(deleteNotification).toHaveBeenCalledWith('9')
    expect(notificationTarget).not.toHaveBeenCalled()
    expect(wrapper.find('.message-card').exists()).toBe(false)
    expect(wrapper.get('.messages-heading').text()).toContain('0 条未读')
    wrapper.unmount()
  })
  it.each([['清理已读消息', true], ['清空历史消息', false]] as const)('批量%s使用全收件箱边界而非当前行', async (label, readOnly) => {
    vi.mocked(notifications).mockResolvedValue(inbox)
    vi.mocked(unreadCount).mockResolvedValue(1)
    vi.mocked(deleteNotificationHistory).mockResolvedValue({ deletedCount: 1 })
    const { wrapper } = await setup('/notifications', true); await flushPromises()
    await wrapper.get('[aria-label="清理消息"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text() === label)!.trigger('click')
    expect(deleteNotificationHistory).not.toHaveBeenCalled()
    await wrapper.findAll('button').find(b => b.text() === '确认删除')!.trigger('click'); await flushPromises()
    expect(deleteNotificationHistory).toHaveBeenCalledWith('12', readOnly)
    wrapper.unmount()
  })
  it('删除失败留在确认框局部提示并允许重试', async () => {
    vi.mocked(notifications).mockResolvedValue(inbox)
    vi.mocked(unreadCount).mockResolvedValue(1)
    vi.mocked(deleteNotification).mockRejectedValueOnce(new Error('网络中断')).mockResolvedValue({ deletedCount: 1 })
    const { wrapper } = await setup('/notifications', true); await flushPromises()
    await wrapper.get('[aria-label="删除消息"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text() === '确认删除')!.trigger('click'); await flushPromises()
    expect(wrapper.get('dialog [role="alert"]').text()).toBe('网络中断')
    expect(wrapper.find('.message-card').exists()).toBe(true)
    await wrapper.findAll('button').find(b => b.text() === '确认删除')!.trigger('click'); await flushPromises()
    expect(deleteNotification).toHaveBeenCalledTimes(2)
    expect(wrapper.find('dialog').exists()).toBe(false)
    wrapper.unmount()
  })
  it('切换账号关闭删除确认，旧请求不能覆盖新收件箱', async () => {
    const pending = deferred<{ deletedCount: number }>()
    vi.mocked(notifications).mockResolvedValueOnce(inbox).mockResolvedValue({ ...inbox, items: [], total: 0, latestId: null })
    vi.mocked(unreadCount).mockResolvedValue(0)
    vi.mocked(deleteNotification).mockReturnValue(pending.promise)
    const { wrapper } = await setup('/notifications', true); await flushPromises()
    await wrapper.get('[aria-label="删除消息"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text() === '确认删除')!.trigger('click')
    useAuthStore().sessionVersion++; await flushPromises()
    pending.resolve({ deletedCount: 1 }); await flushPromises()
    expect(notifications).toHaveBeenCalledTimes(2)
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(wrapper.find('.message-card').exists()).toBe(false)
    expect(wrapper.get('[aria-label="清理消息"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('根评论和回复归在同一部分，显示被回复者并提供主页链接', async () => {
    const author = { id: '100', nickname: '路线作者', avatarUrl: null }
    const child = { id: '4', body: '验证有效', visibility: 'public', author: { id: '101', nickname: '学习者' }, replyToAuthor: author, replyToCommentId: '3', canEdit: false, createdAt: '2026-11-03T00:00:00Z', updatedAt: '2026-11-03T00:00:00Z' }
    vi.mocked(getIssue).mockResolvedValue({ ...topic(), commentCount: 2, comments: { items: [{ ...child, id: '3', body: '资源已更新', author, replyToCommentId: null, replies: { items: [child], total: 1, page: 1, pageSize: 5 } }], total: 1, page: 1, pageSize: 20 } })
    const { wrapper } = await setup('/roadmaps/1/issues/2'); await flushPromises()
    expect(wrapper.findAll('.comment-thread')).toHaveLength(1)
    expect(wrapper.get('.comment-thread .child-reply').text()).toContain('验证有效')
    expect(wrapper.get('.comment-byline .reply-target').text()).toContain('@路线作者')
    expect(wrapper.get('.child-reply .comment-byline a').attributes('href')).toBe('/users/101')
    expect(wrapper.text()).not.toContain('围绕路线交流问题与建议')
    wrapper.unmount()
  })
  it('右侧操作与时间线支持切换，时间线不占正文', async () => {
    vi.mocked(getIssue).mockResolvedValue({ ...topic(), events: [{ id: '10', type: 'closed', fromStatus: 'open', toStatus: 'closed', reason: '重复话题', createdAt: '2026-11-03T00:00:00Z' }] })
    const { wrapper } = await setup('/roadmaps/1/issues/2'); await flushPromises()
    expect(wrapper.find('.topic-main .sidebar-timeline').exists()).toBe(false)
    await wrapper.get('#timeline-tab').trigger('click')
    expect(wrapper.get('.topic-sidebar .sidebar-timeline').text()).toContain('重复话题')
    await wrapper.get('#timeline-tab').trigger('keydown', { key: 'ArrowLeft' })
    expect(wrapper.get('#actions-tab').attributes('aria-selected')).toBe('true')
    wrapper.unmount()
  })
  it('非作者可回复resolved话题，但不显示状态修改', async () => {
    vi.mocked(getIssue).mockResolvedValue(topic('resolved'))
    const { wrapper } = await setup('/roadmaps/1/issues/2'); await flushPromises()
    expect(wrapper.find('#comment-body').exists()).toBe(true)
    expect(wrapper.find('#issue-state').exists()).toBe(false)
    wrapper.unmount()
  })
  it('closed话题不提供新增回复', async () => {
    vi.mocked(getIssue).mockResolvedValue(topic('closed'))
    const { wrapper } = await setup('/roadmaps/1/issues/2'); await flushPromises()
    expect(wrapper.find('#comment-body').exists()).toBe(false)
    expect(wrapper.text()).toContain('话题已关闭')
    wrapper.unmount()
  })
  it('旧服务错误授予处理权限时仍对非路线作者隐藏操作', async () => {
    vi.mocked(getIssue).mockResolvedValue({ ...topic(), canResolve: true, canClose: true, roadmapCreatorId: '888' })
    const { wrapper } = await setup('/roadmaps/1/issues/2'); await flushPromises()
    expect(wrapper.find('#issue-state').exists()).toBe(false)
    wrapper.unmount()
  })
  it('删除的根评论不显示占位，存活的后续回复仍在原楼层', async () => {
    const comment = { id: '3', body: null, visibility: 'deleted', author: null, replyToCommentId: null, canEdit: false, createdAt: '2026-11-03T00:00:00Z', updatedAt: '2026-11-03T00:00:00Z' }
    vi.mocked(getIssue).mockResolvedValue({ ...topic(), comments: { items: [{ ...comment, replies: { items: [{ ...comment, id: '4', body: '存活回复', visibility: 'public', author: { id: '101', nickname: 'A' }, replyToCommentId: '3' }], total: 1, page: 1, pageSize: 5 } }], total: 1, page: 1, pageSize: 20 } })
    const { wrapper } = await setup('/roadmaps/1/issues/2'); await flushPromises()
    expect(wrapper.find('#comment-3').exists()).toBe(false)
    expect(wrapper.get('#comment-4').classes()).toContain('child-reply')
    expect(wrapper.text()).not.toContain('此评论已删除')
    wrapper.unmount()
  })
  it('切换账号清空输入，旧详情迟到时不能覆盖新账号', async () => {
    const old = deferred<IssueDetail>()
    vi.mocked(getIssue).mockReturnValueOnce(old.promise).mockResolvedValue(topic('closed'))
    const { wrapper } = await setup('/roadmaps/1/issues/2')
    const auth = useAuthStore()
    auth.sessionVersion++
    await flushPromises()
    old.resolve({ ...topic(), body: '旧账号私有响应' }); await flushPromises()
    expect(wrapper.text()).not.toContain('旧账号私有响应')
    expect(wrapper.find('#comment-body').exists()).toBe(false)
    wrapper.unmount()
  })
  it('回复分页清除通知锚点并请求目标页', async () => {
    vi.mocked(getIssue).mockResolvedValue({ ...topic(), comments: { items: [], total: 42, page: 1, pageSize: 20 } })
    const { wrapper, router } = await setup('/roadmaps/1/issues/2?commentId=8'); await flushPromises()
    const next = wrapper.findAll('button').find(b => b.text() === '下一页')!
    await next.trigger('click'); await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ page: '2' })
    expect(getIssue).toHaveBeenLastCalledWith('1', '2', { page: 2, commentId: undefined })
    wrapper.unmount()
  })
  it('请求失败保留回复内容，提示用户重试', async () => {
    vi.mocked(getIssue).mockResolvedValue(topic())
    vi.mocked(issueAction).mockRejectedValue(new Error('已关闭话题不能新增回复'))
    const { wrapper } = await setup('/roadmaps/1/issues/2'); await flushPromises()
    await wrapper.get('#comment-body').setValue('未发送的回复')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect((wrapper.get('#comment-body').element as HTMLTextAreaElement).value).toBe('未发送的回复')
    expect(wrapper.get('.comment-composer [role="alert"]').text()).toContain('已关闭话题')
    expect(wrapper.find('.discussion-error').exists()).toBe(false)
    wrapper.unmount()
  })
  it('消息目标受限时显示占位，不跳转原内容', async () => {
    vi.mocked(notifications).mockResolvedValue({ items: [{ id: '9', type: 'comment_created', readAt: null, createdAt: '2026-11-03T00:00:00Z' }], total: 1, page: 1, pageSize: 20 })
    vi.mocked(unreadCount).mockResolvedValue(1)
    vi.mocked(notificationTarget).mockResolvedValue({ accessible: false, path: null, message: '目标内容已受限或不可访问' })
    const { wrapper, router } = await setup('/notifications', true); await flushPromises()
    await wrapper.get('button[aria-label="查看消息"]').trigger('click'); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/notifications')
    expect(wrapper.text()).toContain('目标内容已受限或不可访问')
    expect(readNotification).toHaveBeenCalledWith('9')
    expect(wrapper.get('.message-card [role="alert"]').text()).toContain('目标内容已受限')
    expect(wrapper.get('.message-card').classes()).not.toContain('is-unread')
    wrapper.unmount()
  })
  it('消息面板区分未读与已读，切换筛选只读取列表', async () => {
    const item = { id: '9', type: 'comment_created', readAt: null, createdAt: '2026-11-03T00:00:00Z' }
    vi.mocked(notifications).mockResolvedValueOnce({ items: [item, { ...item, id: '8', readAt: item.createdAt }], total: 2, page: 1, pageSize: 20 }).mockResolvedValue({ items: [item], total: 1, page: 1, pageSize: 20 })
    vi.mocked(unreadCount).mockResolvedValue(1)
    const { wrapper } = await setup('/notifications', true); await flushPromises()
    expect(wrapper.find('.message-board').exists()).toBe(true)
    expect(wrapper.findAll('.message-card.is-unread')).toHaveLength(1)
    await wrapper.get('button[aria-label="仅看未读"]').trigger('click'); await flushPromises()
    expect(notifications).toHaveBeenLastCalledWith(1, true)
    expect(wrapper.get('button[aria-label="仅看未读"]').attributes('aria-pressed')).toBe('true')
    expect(readNotification).not.toHaveBeenCalled()
    expect(readThrough).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('批量已读后更新行状态与计数，不添加成功横栏', async () => {
    const item = { id: '9', type: 'comment_created', readAt: null, createdAt: '2026-11-03T00:00:00Z' }
    vi.mocked(notifications).mockResolvedValueOnce({ items: [item], total: 1, page: 1, pageSize: 20 }).mockResolvedValue({ items: [{ ...item, readAt: item.createdAt }], total: 1, page: 1, pageSize: 20 })
    vi.mocked(unreadCount).mockResolvedValueOnce(1).mockResolvedValue(0)
    vi.mocked(readThrough).mockResolvedValue(undefined)
    const { wrapper } = await setup('/notifications', true); await flushPromises()
    await wrapper.get('button[aria-label="将当前列表及更早消息标为已读"]').trigger('click'); await flushPromises()
    expect(readThrough).toHaveBeenCalledWith('9')
    expect(wrapper.find('.message-card.is-unread').exists()).toBe(false)
    expect(wrapper.get('.messages-heading').text()).toContain('0 条未读')
    expect(wrapper.find('.form-success').exists()).toBe(false)
    wrapper.unmount()
  })
  it('列表空态不创建任何讨论或学习关系', async () => {
    vi.mocked(listIssues).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20, topicCount: 0, closedCount: 0, roadmapTitle: '路线' })
    const { wrapper } = await setup('/roadmaps/1/issues'); await flushPromises()
    expect(wrapper.text()).toContain('还没有话题')
    expect(issueAction).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('未读空态可返回全部消息，加载失败在消息面板重试', async () => {
    vi.mocked(notifications).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
    vi.mocked(unreadCount).mockResolvedValue(0)
    const { wrapper } = await setup('/notifications', true); await flushPromises()
    await wrapper.get('button[aria-label="仅看未读"]').trigger('click'); await flushPromises()
    expect(wrapper.get('.message-state').text()).toContain('没有未读消息')
    await wrapper.findAll('button').find(b => b.text() === '查看全部消息')!.trigger('click'); await flushPromises()
    expect(notifications).toHaveBeenLastCalledWith(1, false)
    vi.mocked(notifications).mockRejectedValueOnce(new Error('服务暂不可用'))
    await wrapper.get('button[aria-label="刷新消息"]').trigger('click'); await flushPromises()
    expect(wrapper.get('.message-board [role="alert"]').text()).toContain('服务暂不可用')
    await wrapper.findAll('button').find(b => b.text() === '重新加载')!.trigger('click'); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
