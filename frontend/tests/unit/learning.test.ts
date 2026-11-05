import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, expect, it, vi } from 'vitest'
import LearningView from '../../src/views/learning/LearningView.vue'
import NodeProgressPanel from '../../src/components/roadmap/NodeProgressPanel.vue'
import HomeView from '../../src/views/personal/HomeView.vue'
import JoinLearningDialog from '../../src/components/roadmap/JoinLearningDialog.vue'
import { changeEnrollment, createStudyRecord, enrollmentContent, enrollmentSummary, learningOverview, savePosition, studyRecords, updateNodeStatus, upgradePreview, upgradeLearning } from '../../src/api/enrollment'
import type { EnrollmentContent, EnrollmentSummary, StudyRecordPage, UpgradePreview } from '../../src/types/enrollment'
import { useAuthStore } from '../../src/stores/auth'
import { ApiError } from '../../src/api/http'
import { dismissUpdatePrompt } from '../../src/api/enrollment'

vi.mock('../../src/api/enrollment', () => ({ enrollmentSummary: vi.fn(), enrollmentContent: vi.fn(),
  changeEnrollment: vi.fn(), updateNodeStatus: vi.fn(), savePosition: vi.fn(), studyRecords: vi.fn(), createStudyRecord: vi.fn(), learningOverview: vi.fn(), upgradePreview: vi.fn(), upgradeLearning: vi.fn(), learningSessions: vi.fn(), dismissUpdatePrompt: vi.fn() }))
function summary(): EnrollmentSummary {
  return { id: '1', roadmapId: '10', sessionId: '20', releaseId: '30', versionNo: 1, title: '学习路线',
    description: null, difficulty: 'beginner', status: 'active', startedAt: '2026-11-01T00:00:00Z',
    abandonedAt: null, completedAt: null, lastNodeId: '32', lastOpenedAt: null, progressVersion: 1,
    contentAvailable: true, writable: true, hasNewVersion: false, currentVersionNo: 1,
    stageCount: 1, nodeCount: 2, completedNodeCount: 0, progressNodeCount: 1, progressPercent: 0 }
}
function records(): StudyRecordPage {
  return { items: [], total: 0, today: new Date().toISOString().slice(0, 10), checkedInToday: false, page: 1, pageSize: 20 }
}
function content(): EnrollmentContent {
  return { enrollment: summary(), connections: [], progress: [], stages: [{ id: '30', title: '阶段', canvasX: 0, canvasY: 0,
    nodes: ['31','32'].map(id => ({ id, title: '节点' + id, content: '正文' + id, canvasX: 0, canvasY: 0, countsTowardProgress: id === '31' })) }] }
}
beforeEach(() => {
  vi.resetAllMocks(); setActivePinia(createPinia())
  HTMLElement.prototype.scrollTo = vi.fn()
  HTMLDialogElement.prototype.showModal = vi.fn(); HTMLDialogElement.prototype.close = vi.fn()
  const auth = useAuthStore()
  auth.user = { id: '1', username: 'learner', nickname: '学习者', role: 'user', status: 'active', createdAt: '2026-11-01T00:00:00Z' }
  vi.mocked(enrollmentSummary).mockResolvedValue(summary())
  vi.mocked(enrollmentContent).mockResolvedValue(content())
  vi.mocked(savePosition).mockResolvedValue(summary())
  vi.mocked(studyRecords).mockResolvedValue(records())
})
async function setup(home = false) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/learning', component: { template: '<p>列表</p>' } },
    { path: '/learning/:id', name: 'learning-content', component: LearningView },
    { path: '/learning/:id/history', name: 'learning-history', component: { template: '<p>打卡历史</p>' } },
    { path: '/dashboard', name: 'dashboard', component: HomeView },
  ] })
  await router.push(home ? '/dashboard' : '/learning/1'); await router.isReady()
  return { router, wrapper: mount(home ? HomeView : LearningView, { global: { plugins: [router] } }) }
}
it('恢复服务端位置而非首个未完成节点，浏览不完成也不打卡', async () => {
  const { wrapper } = await setup(); await flushPromises()
  expect(wrapper.get('.reader-content-body').text()).toContain('正文32')
  expect(savePosition).toHaveBeenCalledWith('1', '20', '32')
  expect(createStudyRecord).not.toHaveBeenCalled()
  expect(updateNodeStatus).not.toHaveBeenCalled()
  expect(wrapper.find('textarea').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('笔记')
  wrapper.unmount()
})

it('忽略所见新版提示后保留新版标记与查看差异入口', async () => {
  const state = { ...summary(), hasNewVersion: true, currentVersionNo: 2, currentReleaseId: '40', updatePromptDismissed: false }
  vi.mocked(enrollmentSummary).mockResolvedValue(state)
  vi.mocked(enrollmentContent).mockResolvedValue({ ...content(), enrollment: state })
  vi.mocked(dismissUpdatePrompt).mockResolvedValue({ ...state, updatePromptDismissed: true })
  const { wrapper } = await setup(); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '忽略本版提示')!.trigger('click'); await flushPromises()
  expect(dismissUpdatePrompt).toHaveBeenCalledWith('1', '40', true)
  expect(wrapper.text()).toContain('新版 V2')
  expect(wrapper.text()).not.toContain('新版不会自动替换你的学习内容')
  expect(wrapper.findAll('button').some(button => button.text() === '查看版本差异')).toBe(true)
  expect(wrapper.findAll('button').some(button => button.text() === '恢复更新提示')).toBe(true)
  wrapper.unmount()
})
it('完成与撤销都携带当前会话，主线数字与环保持一致', async () => {
  const { wrapper } = await setup(); await flushPromises()
  vi.mocked(updateNodeStatus).mockResolvedValue({ ...summary(), completedNodeCount: 1, progressPercent: 100, progressVersion: 2 })
  await wrapper.findAll('button').find(b => b.text() === '完成此节点')!.trigger('click'); await flushPromises()
  expect(updateNodeStatus).toHaveBeenCalledWith('1', '20', '32', true)
  expect(wrapper.get('.progress-ring').text()).toBe('100%')
  expect(wrapper.text()).toContain('主线已完成 1 / 1')
  vi.mocked(updateNodeStatus).mockResolvedValue(summary())
  await wrapper.findAll('button').find(b => b.text() === '撤销完成')!.trigger('click'); await flushPromises()
  expect(updateNodeStatus).toHaveBeenLastCalledWith('1', '20', '32', false)
  expect(wrapper.get('.progress-ring').text()).toBe('0%')
  expect(createStudyRecord).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('旧会话冲突立即清空正文并提供刷新入口', async () => {
  const { wrapper } = await setup(); await flushPromises()
  vi.mocked(updateNodeStatus).mockRejectedValue(new ApiError('版本已变化', 409, 'LEARNING_SESSION_CHANGED'))
  await wrapper.findAll('button').find(b => b.text() === '完成此节点')!.trigger('click'); await flushPromises()
  expect(wrapper.find('.reader-content-body').exists()).toBe(false)
  expect(wrapper.text()).toContain('重新加载')
  wrapper.unmount()
})
it('打卡响应丢失可按同一会话重试，成功后禁用当天按钮', async () => {
  vi.mocked(createStudyRecord).mockRejectedValueOnce(new ApiError('响应丢失', 0, 'NETWORK_ERROR'))
    .mockResolvedValue({ id: '1', sessionId: '20', checkinDate: records().today, timezoneName: 'Asia/Shanghai', isValid: true, createdAt: '2026-11-01T00:00:00Z' })
  const { wrapper } = await setup(); await flushPromises()
  const button = () => wrapper.get('.route-checkin-panel .primary-button')
  await button().trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('响应丢失')
  vi.mocked(studyRecords).mockResolvedValue({ ...records(), checkedInToday: true, total: 1 })
  await button().trigger('click'); await flushPromises()
  expect(createStudyRecord).toHaveBeenCalledTimes(2)
  expect(createStudyRecord).toHaveBeenLastCalledWith('1', '20')
  expect(button().text()).toBe('今日已打卡')
  expect(button().attributes('disabled')).toBeDefined()
  wrapper.unmount()
})
it('退出确认可取消，恢复使用原会话', async () => {
  const { wrapper } = await setup(); await flushPromises()
  await wrapper.findAll('button').find(b => b.text() === '退出学习')!.trigger('click')
  await wrapper.findAll('dialog button').find(b => b.text() === '取消')!.trigger('click')
  expect(changeEnrollment).not.toHaveBeenCalled()
  wrapper.unmount()
  vi.mocked(enrollmentSummary).mockResolvedValue({ ...summary(), status: 'abandoned', writable: false })
  vi.mocked(enrollmentContent).mockResolvedValue({ ...content(), enrollment: { ...summary(), status: 'abandoned', writable: false } })
  vi.mocked(changeEnrollment).mockResolvedValue(summary())
  const restored = await setup(); await flushPromises()
  await restored.wrapper.findAll('button').find(b => b.text() === '恢复原版学习')!.trigger('click'); await flushPromises()
  expect(changeEnrollment).toHaveBeenCalledWith('1','20','restore')
  restored.wrapper.unmount()
})
it('账号切换后迟到正文与统计不会显示', async () => {
  let resolve!: (value: EnrollmentContent) => void
  vi.mocked(enrollmentContent).mockReturnValueOnce(new Promise(done => { resolve = done }))
  const { wrapper } = await setup(); await flushPromises()
  useAuthStore().clear(); await flushPromises()
  resolve(content()); await flushPromises()
  expect(wrapper.text()).not.toContain('正文32')
  expect(wrapper.find('.route-checkin-panel').exists()).toBe(false)
  wrapper.unmount()
})
it('下架不请求正文且保留本人打卡记录入口', async () => {
  vi.mocked(enrollmentSummary).mockResolvedValue({ ...summary(), contentAvailable: false, writable: false, title: '内容已下架' })
  const { wrapper } = await setup(); await flushPromises()
  expect(enrollmentContent).not.toHaveBeenCalled()
  expect(wrapper.find('a[href="/learning/1/history"]').exists()).toBe(true)
  wrapper.unmount()
})
it('节点工具只提供完成与撤销，没有旧记录表单', async () => {
  const wrapper = mount(NodeProgressPanel, { props: { completed: true, node: content().stages[0]!.nodes[0], busy: false, writable: true } })
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('status')?.[0]).toEqual(['31', false])
  expect(wrapper.find('textarea').exists()).toBe(false)
  wrapper.unmount()
})
it('本人日历显示有效日期与统计，退出清除私人数据', async () => {
  vi.mocked(learningOverview).mockResolvedValue({ learningRoadmapCount: 1, completedNodeCount: 2, checkinDayCount: 3, currentStreak: 2, longestStreak: 3, today: '2026-11-02', month: '2026-11', calendarDates: ['2026-11-01', '2026-11-02'] })
  const { wrapper } = await setup(true); await flushPromises()
  expect(wrapper.findAll('.calendar-grid .checked')).toHaveLength(2)
  expect(wrapper.text()).toContain('最长连续天数')
  useAuthStore().clear(); await flushPromises()
  expect(wrapper.find('.calendar-grid').exists()).toBe(false)
  wrapper.unmount()
})

function preview(): UpgradePreview {
  return { sourceSessionId: '20', targetReleaseId: '40', sourceVersionNo: 1, targetVersionNo: 3,
    progressVersion: 7, updateSummary: '学习目标调整', sourceCompleted: 1, sourceTotal: 2, sourcePercent: 50,
    targetTotal: 3, completedMin: 0, completedMax: 1, percentMin: 0, percentMax: 33,
    stageChanges: [], releaseChanges: [], connectionsChanged: false,
    nodeChanges: [{ stableKey: 'cc9a58f2-9490-43fd-a243-fa521a8c02bf', sourceTitle: '基础', targetTitle: '新任务',
      sourceStage: '阶段', targetStage: '阶段', changes: ['semantic'], isCompleted: true,
      requiresConfirmation: true, targetCountsTowardProgress: true }] }
}
function upgradeResult() { return { sourceSessionId: '20', targetSessionId: '50', targetReleaseId: '40', versionNo: 3,
  progressVersion: 1, completedNodeCount: 1, progressNodeCount: 3, progressPercent: 33, lastNodeId: '41' } }

it('语义变化必须明确选择，暂不升级只关闭且不提交', async () => {
  vi.mocked(upgradePreview).mockResolvedValue(preview())
  const wrapper = mount(JoinLearningDialog, { props: { enrollmentId: '1' } }); await flushPromises()
  const confirm = () => wrapper.findAll('button').find(button => button.text() === '确认升级')!
  expect(confirm().attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain('当前：1 / 2 · 50%')
  await wrapper.get('select').setValue('keep')
  expect(wrapper.text()).toContain('升级后：1 / 3 · 33%')
  await wrapper.findAll('button').find(button => button.text() === '暂不升级')!.trigger('click')
  expect(wrapper.emitted('close')).toHaveLength(1)
  expect(upgradeLearning).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('升级响应丢失冻结选择并沿用相同请求键重试', async () => {
  vi.mocked(upgradePreview).mockResolvedValue(preview())
  vi.mocked(upgradeLearning).mockRejectedValueOnce(new ApiError('响应丢失', 0, 'NETWORK_ERROR')).mockResolvedValue(upgradeResult())
  const wrapper = mount(JoinLearningDialog, { props: { enrollmentId: '1' } }); await flushPromises()
  await wrapper.get('select').setValue('keep')
  await wrapper.findAll('button').find(button => button.text() === '确认升级')!.trigger('click'); await flushPromises()
  expect(wrapper.get('select').attributes('disabled')).toBeDefined()
  await wrapper.findAll('button').find(button => button.text() === '重试本次升级')!.trigger('click'); await flushPromises()
  const calls = vi.mocked(upgradeLearning).mock.calls
  expect(calls).toHaveLength(2)
  expect(calls[1]).toEqual(calls[0])
  expect(calls[0]![1]).toMatchObject({ sourceSessionId: '20', targetReleaseId: '40', progressVersion: 7,
    confirmations: [{ stableKey: preview().nodeChanges[0]!.stableKey, action: 'keep' }] })
  expect(wrapper.emitted('upgraded')).toHaveLength(1)
  wrapper.unmount()
})

it('过期预览需重新查看差异并重新确认，不能自动提交旧选择', async () => {
  vi.mocked(upgradePreview).mockResolvedValueOnce(preview()).mockResolvedValue({ ...preview(), progressVersion: 8 })
  vi.mocked(upgradeLearning).mockRejectedValue(new ApiError('进度变化，请重新预览', 409, 'UPGRADE_PREVIEW_EXPIRED'))
  const wrapper = mount(JoinLearningDialog, { props: { enrollmentId: '1' } }); await flushPromises()
  await wrapper.get('select').setValue('relearn')
  await wrapper.findAll('button').find(button => button.text() === '确认升级')!.trigger('click'); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '重新查看差异')!.trigger('click'); await flushPromises()
  expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('')
  expect(upgradeLearning).toHaveBeenCalledTimes(1)
  expect(wrapper.findAll('button').find(button => button.text() === '确认升级')!.attributes('disabled')).toBeDefined()
  wrapper.unmount()
})

it('历史会话只读浏览不保存位置且没有退出或恢复入口', async () => {
  const { wrapper, router } = await setup(); await flushPromises()
  vi.mocked(savePosition).mockClear()
  const old = { ...summary(), sessionId: '19', isCurrentSession: false, writable: false }
  vi.mocked(enrollmentSummary).mockResolvedValue(old)
  vi.mocked(enrollmentContent).mockResolvedValue({ ...content(), enrollment: old })
  await router.push('/learning/1?session=19'); await flushPromises()
  expect(enrollmentContent).toHaveBeenLastCalledWith('1', '19')
  expect(wrapper.text()).toContain('这是历史学习版本，仅供回顾')
  expect(savePosition).not.toHaveBeenCalled()
  expect(wrapper.findAll('button').some(button => ['退出学习', '恢复原版学习'].includes(button.text()))).toBe(false)
  expect(wrapper.get('.learning-node-tools button').attributes('disabled')).toBeDefined()
  wrapper.unmount()
})

it('升级差异迟到时已关闭弹窗不会重新出现或触发升级', async () => {
  let resolve!: (value: UpgradePreview) => void
  vi.mocked(upgradePreview).mockReturnValue(new Promise(done => { resolve = done }))
  const wrapper = mount(JoinLearningDialog, { props: { enrollmentId: '1' } }); await flushPromises()
  wrapper.unmount()
  resolve(preview()); await flushPromises()
  expect(upgradeLearning).not.toHaveBeenCalled()
  expect(wrapper.emitted('upgraded')).toBeUndefined()
})

it('升级响应丢失后关闭会刷新服务端当前学习，不宣称取消已提交操作', async () => {
  vi.mocked(upgradePreview).mockResolvedValue(preview())
  vi.mocked(upgradeLearning).mockRejectedValue(new ApiError('响应丢失', 0, 'NETWORK_ERROR'))
  const wrapper = mount(JoinLearningDialog, { props: { enrollmentId: '1' } }); await flushPromises()
  await wrapper.get('select').setValue('keep')
  await wrapper.findAll('button').find(button => button.text() === '确认升级')!.trigger('click'); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '关闭并刷新')!.trigger('click')
  expect(wrapper.emitted('upgraded')).toHaveLength(1)
  expect(wrapper.emitted('close')).toBeUndefined()
  expect(upgradeLearning).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})
