import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import * as api from '../../src/api/roadmap'
import { useAuthStore } from '../../src/stores/auth'
import AdminRoadmapsView from '../../src/views/roadmap/AdminRoadmapsView.vue'
import AdminRoadmapDetailView from '../../src/views/roadmap/AdminRoadmapDetailView.vue'
import AdminLayout from '../../src/layouts/AdminLayout.vue'

vi.mock('../../src/api/roadmap', () => ({ adminRoadmaps: vi.fn(), adminRoadmapDetail: vi.fn(), disableRoadmap: vi.fn(), restoreRoadmap: vi.fn() }))
beforeEach(() => {
  setActivePinia(createPinia())
  useAuthStore().user = { id: '7', username: 'admin', nickname: '测试管理员', role: 'admin', status: 'active', createdAt: '' }
  vi.mocked(api.adminRoadmaps).mockReset().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 12 })
  Object.assign(HTMLDialogElement.prototype, { showModal(this: HTMLDialogElement) { this.open = true }, close(this: HTMLDialogElement) { this.open = false } })
})
afterEach(() => vi.clearAllMocks())
async function setup(component: typeof AdminRoadmapsView | typeof AdminRoadmapDetailView | typeof AdminLayout) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/admin/roadmaps', component: AdminRoadmapsView },
    { path: '/admin/roadmaps/:id', component: AdminRoadmapDetailView },
    { path: '/admin/users', component: { template: '<p />' } },
    { path: '/admin/official-roadmaps', component: { template: '<p />' } },
    { path: '/admin/system', component: { template: '<p />' } },
    { path: '/admin/reports', component: { template: '<p />' } },
  ] })
  await router.push(component === AdminRoadmapDetailView ? '/admin/roadmaps/12' : '/admin/roadmaps')
  const wrapper = mount(component, { global: { plugins: [router], stubs: { RoadmapContentReader: true } } })
  await flushPromises()
  return { wrapper, router }
}
it('列表提交搜索、难度和排序，重置后恢复第一页', async () => {
  const { wrapper } = await setup(AdminRoadmapsView)
  await wrapper.get('[aria-label="搜索路线标题"]').setValue('Python')
  await wrapper.findAll('select')[0]!.setValue('advanced')
  await flushPromises()
  expect(api.adminRoadmaps).toHaveBeenLastCalledWith(expect.objectContaining({ keyword: 'Python', difficulty: 'advanced', page: 1 }))
  await wrapper.findAll('select')[2]!.setValue('title')
  await flushPromises()
  expect(api.adminRoadmaps).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: 'title' }))
  await wrapper.get('.admin-reset').trigger('click'); await flushPromises()
  expect(api.adminRoadmaps).toHaveBeenLastCalledWith(expect.objectContaining({ keyword: '', difficulty: undefined, sortBy: 'publishedAt' }))
  wrapper.unmount()
})
it('账号变化后迟到的旧列表不能回填', async () => {
  let finish!: (value: Awaited<ReturnType<typeof api.adminRoadmaps>>) => void
  vi.mocked(api.adminRoadmaps).mockReturnValueOnce(new Promise(done => { finish = done }))
  const { wrapper } = await setup(AdminRoadmapsView)
  useAuthStore().clear(); await flushPromises()
  finish({ items: [], total: 999, page: 1, pageSize: 12 }); await flushPromises()
  expect(wrapper.text()).not.toContain('999')
  wrapper.unmount()
})
it('请求失败显示重试，后续成功显示空态', async () => {
  vi.mocked(api.adminRoadmaps).mockRejectedValueOnce(new Error('网络中断'))
  const { wrapper } = await setup(AdminRoadmapsView)
  expect(wrapper.get('[role="alert"]').text()).toContain('网络中断')
  await wrapper.get('[role="alert"] button').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('没有符合条件的路线')
  wrapper.unmount()
})
it('侧栏为独立对话层，Escape关闭并恢复触发器焦点', async () => {
  const { wrapper } = await setup(AdminLayout)
  await wrapper.get('[aria-label="展开管理侧栏"]').trigger('click'); await flushPromises()
  expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')
  expect(wrapper.get('main').attributes('inert')).toBeDefined()
  await wrapper.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
  expect(wrapper.find('#admin-drawer').exists()).toBe(false)
  expect(wrapper.find('main').attributes('inert')).toBeUndefined()
  wrapper.unmount()
})
it('取消下架不发送请求，失败保留原因供重试', async () => {
  vi.mocked(api.adminRoadmapDetail).mockResolvedValue({ id: '12', title: '审核路线', status: 'published', editVersion: 3,
    author: { id: '1', username: 'author', nickname: '作者' }, releases: [], stages: [], connections: [], moderationHistory: [] } as unknown as Awaited<ReturnType<typeof api.adminRoadmapDetail>>)
  const { wrapper } = await setup(AdminRoadmapDetailView)
  await wrapper.get('.review-heading button').trigger('click')
  await wrapper.get('.app-dialog footer button').trigger('click')
  expect(api.disableRoadmap).not.toHaveBeenCalled()
  await wrapper.get('.review-heading button').trigger('click')
  await wrapper.get('textarea').setValue('审核原因')
  vi.mocked(api.disableRoadmap).mockRejectedValueOnce(new Error('版本冲突，请重新加载'))
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('版本冲突')
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('审核原因')
  wrapper.unmount()
})
