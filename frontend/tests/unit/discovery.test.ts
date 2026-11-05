import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DiscoveryView from '../../src/views/roadmap/DiscoveryView.vue'
import DetailView from '../../src/views/roadmap/DetailView.vue'
import { ApiError } from '../../src/api/http'
import { changeFavorite, myFavorites, publicRoadmaps, roadmapDetail } from '../../src/api/roadmap'
import { useAuthStore } from '../../src/stores/auth'
import type { FavoriteItem, PublicRoadmap, RoadmapDetail } from '../../src/types/roadmap'
import type { Page } from '../../src/types/common'

vi.mock('../../src/api/roadmap', () => ({ publicRoadmaps: vi.fn(), myFavorites: vi.fn(), changeFavorite: vi.fn(), roadmapDetail: vi.fn() }))
vi.mock('../../src/api/user', async importOriginal => ({ ...await importOriginal<typeof import('../../src/api/user')>(), roadmapSubscription: vi.fn().mockResolvedValue({ subscribed: false }) }))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
function card(title: string): PublicRoadmap {
  return { id: '123', title, description: '', difficulty: 'beginner', coverUrl: null, roadmapType: 'user',
    releaseId: '789', versionNo: 1, publishedAt: '2026-11-01T00:00:00Z', stageCount: 1, nodeCount: 1,
    learnerCount: 0, favoriteCount: 0, isFavorited: false, isOwner: false,
    author: { id: '456', username: 'author', nickname: '作者' } }
}
const result = <T>(items: T[], total = items.length): Page<T> => ({ items, total, page: 1, pageSize: 12 })

beforeEach(() => { vi.resetAllMocks(); setActivePinia(createPinia()) })

async function setup(path = '/') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', name: 'community', component: DiscoveryView },
    { path: '/favorites', name: 'favorites', component: DiscoveryView },
    { path: '/login', component: { template: '<p>登录</p>' } },
    { path: '/roadmaps/:id', name: 'roadmap-detail', component: { template: '<p>详情</p>' } },
    { path: '/roadmaps', component: { template: '<p>仓库</p>' } },
    { path: '/users/:userId', name: 'user-profile', component: { template: '<p>个人主页</p>' } },
  ] })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(DiscoveryView, { global: { plugins: [router] } })
  return { wrapper, router }
}

describe('社区和收藏异步边界', () => {
  it.each(['/', '/favorites'])('卡片统计移至左下角，头像和作者名独立跳转主页：%s', async path => {
    const roadmap = { ...card('公开路线'), favoriteCount: 12, learnerCount: 34 }
    vi.mocked(publicRoadmaps).mockResolvedValue(result([roadmap]))
    vi.mocked(myFavorites).mockResolvedValue(result([{ roadmapId: roadmap.id, title: roadmap.title, status: 'published', accessible: true, favoritedAt: '', roadmap }]))
    const { wrapper, router } = await setup(path); await flushPromises()
    const stats = wrapper.get('.fresh-social-stats')
    expect(stats.text()).toContain('12 人收藏')
    expect(stats.text()).toContain('34 人学习')
    const button = wrapper.get('.discovery-card-footer button')
    expect(button.text()).toBe(path === '/favorites' ? '取消收藏' : '收藏')
    expect(wrapper.get('.fresh-author').attributes('href')).toBe('/users/456')
    await wrapper.get('.fresh-author .user-avatar').trigger('click'); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/users/456')
    await router.push(path); await flushPromises()
    await wrapper.get('.fresh-author-name').trigger('click'); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/users/456')
    expect(changeFavorite).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('收藏成功由按钮反馈，不插入页面提示横栏', async () => {
    const auth = useAuthStore()
    auth.user = { id: '100', username: 'first', nickname: '测试用户', role: 'user', status: 'active', createdAt: '' }
    vi.mocked(publicRoadmaps).mockResolvedValue(result([card('公开路线')]))
    vi.mocked(changeFavorite).mockResolvedValue({ roadmapId: '123', isFavorited: true, favoriteCount: 1 })
    const { wrapper } = await setup(); await flushPromises()
    await wrapper.get('button[aria-label="收藏：公开路线"]').trigger('click'); await flushPromises()
    expect(wrapper.get('button[aria-label="取消收藏：公开路线"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('.fresh-social-stats').text()).toContain('1 人收藏')
    expect(wrapper.get('button[aria-label="取消收藏：公开路线"]').text()).toBe('已收藏')
    expect(wrapper.find('.route-info').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('我的收藏”中查看')
    wrapper.unmount()
  })
  it('收藏失败只在对应卡片显示错误，重试成功后移除', async () => {
    const auth = useAuthStore()
    auth.user = { id: '100', username: 'first', nickname: '测试用户', role: 'user', status: 'active', createdAt: '' }
    vi.mocked(publicRoadmaps).mockResolvedValue(result([card('公开路线')]))
    vi.mocked(changeFavorite).mockRejectedValueOnce(new Error('网络暂不可用')).mockResolvedValueOnce({ roadmapId: '123', isFavorited: true, favoriteCount: 1 })
    const { wrapper } = await setup(); await flushPromises()
    await wrapper.get('button[aria-label="收藏：公开路线"]').trigger('click'); await flushPromises()
    expect(wrapper.get('.discovery-card [role="alert"]').text()).toContain('网络暂不可用')
    await wrapper.get('button[aria-label="收藏：公开路线"]').trigger('click'); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('游客收藏进入登录页且不会自动收藏', async () => {
    vi.mocked(publicRoadmaps).mockResolvedValue(result([card('公开路线')]))
    const { wrapper, router } = await setup('/?q=Python')
    await flushPromises()
    await wrapper.get('button[aria-label="收藏：公开路线"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query).toEqual({})
    expect(changeFavorite).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('社区只展示路线，不展示个人学习进度或聚合问答', async () => {
    vi.mocked(publicRoadmaps).mockResolvedValue(result([card('公开路线')]))
    const { wrapper } = await setup()
    await flushPromises()
    expect(wrapper.text()).toContain('公开路线')
    for (const text of ['继续学习', '社区共建', '公开问答', '学习进度']) {
      expect(wrapper.text()).not.toContain(text)
    }
    wrapper.unmount()
  })
  it('快速切换搜索时迟到结果不会覆盖新搜索', async () => {
    const old = deferred<Page<PublicRoadmap>>()
    vi.mocked(publicRoadmaps).mockReturnValueOnce(old.promise).mockResolvedValueOnce(result([card('新的路线')]))
    const { wrapper, router } = await setup('/?q=old')
    await router.push('/?q=new')
    await flushPromises()
    expect(wrapper.text()).toContain('新的路线')
    old.resolve(result([card('过期路线')]))
    await flushPromises()
    expect(wrapper.text()).not.toContain('过期路线')
    expect(wrapper.text()).toContain('新的路线')
    wrapper.unmount()
  })

  it('切换账号时立即清空旧收藏，迟到的私人数据不显示', async () => {
    const auth = useAuthStore()
    auth.user = { id: '100', username: 'first', nickname: '测试用户', role: 'user', status: 'active', createdAt: '' }
    const old = deferred<Page<FavoriteItem>>()
    vi.mocked(myFavorites).mockReturnValueOnce(old.promise).mockResolvedValueOnce(result([]))
    const { wrapper } = await setup('/favorites')
    auth.user = { ...auth.user!, id: '101', username: 'second' }
    await flushPromises()
    old.resolve(result([{ roadmapId: '123', title: '前账号私人收藏', status: 'published', accessible: true,
      favoritedAt: '2026-11-01T00:00:00Z', roadmap: card('前账号私人收藏') }]))
    await flushPromises()
    expect(wrapper.text()).toContain('还没有收藏路线')
    expect(wrapper.text()).not.toContain('前账号私人收藏')
    wrapper.unmount()
  })

  it('取消收藏后页数减少时自动回到最后一页', async () => {
    vi.mocked(myFavorites).mockResolvedValueOnce(result([], 12)).mockResolvedValueOnce(result([
      { roadmapId: '123', title: '保留的收藏', status: 'published', accessible: true, favoritedAt: '', roadmap: card('保留的收藏') },
    ], 12))
    const { wrapper, router } = await setup('/favorites?page=2')
    await flushPromises()
    expect(router.currentRoute.value.query.page).toBeUndefined()
    expect(wrapper.text()).toContain('保留的收藏')
    wrapper.unmount()
  })
})

describe('统一路线详情与身份操作', () => {
  function detail(owner = false, draft = false): RoadmapDetail {
    return { ...card('路线详情'), status: 'published', displayStatus: '已发布', editVersion: 1, updatedAt: '2026-11-03T00:00:00Z',
      publishedAt: '2026-11-03T00:00:00Z', authorArchivedAt: null, disabledReason: null, canDelete: false,
      isOwner: owner, canMaintain: owner, canFavorite: !owner, canStartLearning: !owner,
      canReadContent: draft, contentSource: draft ? 'draft' : null, hasUnpublishedChanges: draft,
      updateSummary: '首次发布版本说明', favoriteCount: 12, learnerCount: 34,
      stages: [{ id: '1', title: '基础', canvasX: 0, canvasY: 0, nodes: [] }], connections: [] }
  }
  async function setupDetail(owner = false) {
    useAuthStore().user = { id: owner ? '456' : '100', username: 'viewer', nickname: '用户', role: 'user', status: 'active', createdAt: '' }
    vi.mocked(roadmapDetail).mockImplementation(async (_id, _enrollment, preview) => detail(owner, preview === 'draft'))
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', component: { template: '<p>社区</p>' } },
      { path: '/roadmaps', component: { template: '<p>创作</p>' } },
      { path: '/roadmaps/:id', name: 'roadmap-detail', component: DetailView },
      { path: '/roadmaps/:id/edit', name: 'roadmap-editor', component: { template: '<p>编辑</p>' } },
      { path: '/roadmaps/:id/browse', name: 'roadmap-browse', component: { template: '<p>预览</p>' } },
      { path: '/roadmaps/:id/issues', component: { template: '<p>讨论</p>' } },
      { path: '/users/:userId', name: 'user-profile', component: { template: '<p>主页</p>' } },
    ] })
    await router.push('/roadmaps/123'); await router.isReady()
    const wrapper = mount(DetailView, { global: { plugins: [router], stubs: { RoadmapCanvas: true } } })
    await flushPromises()
    return { wrapper, router }
  }
  it('作者从普通详情地址直接获得工作稿管理、真实人数，不出现二次管理入口', async () => {
    const { wrapper, router } = await setupDetail(true)
    expect(router.currentRoute.value.fullPath).toBe('/roadmaps/123')
    expect(roadmapDetail).toHaveBeenCalledWith('123', undefined, 'draft')
    expect(wrapper.text()).toContain('编辑工作稿')
    expect(wrapper.text()).toContain('预览工作稿')
    expect(wrapper.text()).not.toContain('管理工作稿')
    expect(wrapper.find('button[aria-pressed]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="路线概况"]').text()).toContain('34')
    expect(wrapper.get('[aria-label="路线概况"]').text()).toContain('12')
    expect(wrapper.find('[aria-label="路线目录"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('学习者仅显示公开内容操作，隐藏发布状态及默认版本说明，点击版本展开', async () => {
    const { wrapper } = await setupDetail()
    expect(roadmapDetail).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('开始学习')
    expect(wrapper.text()).not.toContain('编辑工作稿')
    expect(wrapper.find('.route-badge').exists()).toBe(false)
    expect(wrapper.find('[aria-label="路线目录"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="版本说明"]').exists()).toBe(false)
    const version = wrapper.get('button[aria-controls="route-version-details"]')
    await version.trigger('click')
    expect(wrapper.get('[aria-label="版本说明"]').text()).toContain('首次发布版本说明')
    await version.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[aria-label="版本说明"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('未公开路线由后端重新验证本人身份后在同一详情页承接', async () => {
    const { wrapper, router } = await setupDetail(true)
    vi.mocked(roadmapDetail).mockRejectedValueOnce(new ApiError('不可公开访问', 404, 'ROADMAP_NOT_FOUND')).mockResolvedValueOnce({ ...detail(true, true), status: 'draft', versionNo: null })
    await router.push('/roadmaps/124'); await flushPromises()
    expect(roadmapDetail).toHaveBeenLastCalledWith('124', undefined, 'draft')
    expect(wrapper.text()).toContain('编辑工作稿')
    wrapper.unmount()
  })
  it('切换账号后迟到的作者工作稿不能覆盖学习者详情', async () => {
    const { wrapper, router } = await setupDetail(true)
    const pending = deferred<RoadmapDetail>()
    vi.mocked(roadmapDetail).mockResolvedValueOnce(detail(true)).mockReturnValueOnce(pending.promise).mockResolvedValue(detail())
    await router.push('/roadmaps/124'); await flushPromises()
    const auth = useAuthStore()
    auth.user = { ...auth.user!, id: '100' }; await flushPromises()
    pending.resolve({ ...detail(true, true), title: '旧作者未公开的工作稿' }); await flushPromises()
    expect(wrapper.text()).not.toContain('旧作者未公开的工作稿')
    expect(wrapper.text()).not.toContain('编辑工作稿')
    expect(wrapper.text()).toContain('开始学习')
    wrapper.unmount()
  })
})
