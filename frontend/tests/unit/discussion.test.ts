import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import HomeView from '../../src/views/personal/HomeView.vue'
import { useAuthStore } from '../../src/stores/auth'
import * as social from '../../src/api/user'
import DiscussionBody from '../../src/components/common/DiscussionBody.vue'
import { discussionTokens, safeDiscussionUrl } from '../../src/domain/discussion'

vi.mock('../../src/api/user', () => ({ getPublicProfile: vi.fn(), getActivities: vi.fn(), getFollowing: vi.fn(), getRelationships: vi.fn(), getPublicCollection: vi.fn(), getMyDiscussions: vi.fn(), changeFollow: vi.fn() }))

const profile = (id = '2'): social.PublicProfile => ({ id, username: 'author_' + id, nickname: '作者' + id, avatarUrl: null, bio: '学习与分享', isFollowing: false, followerCount: 0, followingCount: 0, canFollow: true, canViewFavorites: true, canViewLearning: true, favoriteCount: 0, learningCount: 0, roadmaps: { items: [], total: 0, page: 1, pageSize: 12 } })
beforeEach(() => { vi.resetAllMocks(); vi.mocked(social.getActivities).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 10 }); setActivePinia(createPinia()); useAuthStore().user = { id: '1', username: 'viewer', nickname: '查看者', role: 'user', status: 'active', createdAt: '' } })
async function home(path = '/users/2') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/users/:userId', name: 'user-profile', component: HomeView },
    { path: '/users/:userId/following', name: 'user-following', component: HomeView },
    { path: '/users/:userId/followers', name: 'user-followers', component: HomeView },
    { path: '/profile', name: 'profile', component: HomeView },
    { path: '/:pathMatch(.*)*', component: { template: '<div />' } },
  ] })
  await router.push(path); await router.isReady()
  const wrapper = mount(HomeView, { attachTo: document.body, global: { plugins: [router] } }); await flushPromises()
  return { wrapper, router }
}

describe('R09作者主页', () => {
  it('主页固定纵排作品和动态，左侧三项进入独立列表', async () => {
    vi.mocked(social.getPublicProfile).mockResolvedValue(profile())
    const { wrapper } = await home()
    expect(wrapper.find('.profile-tabs').exists()).toBe(false)
    expect(wrapper.findAll('.profile-content-column > section').map(item => item.find('h2').text())).toEqual(['路线作品', '最近动态'])
    expect(wrapper.findAll('.profile-public-counts a').map(item => item.attributes('href'))).toEqual(['/users/2/routes', '/users/2/collections/favorite', '/users/2/collections/learning'])
    expect(social.getPublicProfile).toHaveBeenCalledWith('2', 1, 4)
    expect(social.getActivities).toHaveBeenCalledWith('2', 1, 10)
    wrapper.unmount()
  })
  it('他人私密收藏学习整行隐藏，本人入口保留', async () => {
    vi.mocked(social.getPublicProfile).mockResolvedValue({ ...profile(), canViewFavorites: false, canViewLearning: false, favoriteCount: null, learningCount: null })
    const { wrapper, router } = await home()
    expect(wrapper.findAll('.profile-public-counts a')).toHaveLength(1)
    expect(wrapper.findAll('.follow-counts a').map(item => item.attributes('href'))).toEqual(['/users/2/followers', '/users/2/following'])
    vi.mocked(social.getPublicProfile).mockResolvedValue({ ...profile('1'), canViewFavorites: false, canViewLearning: false })
    await router.push('/profile'); await flushPromises()
    expect(wrapper.findAll('.profile-public-counts a')).toHaveLength(3)
    wrapper.unmount()
  })
  it('关注双向列表使用查看者状态，自己不显示按钮，取消后刷新列表和数量', async () => {
    vi.mocked(social.getPublicProfile).mockResolvedValue({ ...profile(), followingCount: 2 })
    const member = { id: '3', username: 'member', nickname: '其他成员', avatarUrl: null, bio: '简介', isFollowing: true, canFollow: true }
    const myself = { ...member, id: '1', nickname: '查看者', isFollowing: false, canFollow: false }
    vi.mocked(social.getRelationships).mockResolvedValue({ items: [member, myself], total: 2, page: 1, pageSize: 12 })
    const { wrapper, router } = await home('/users/2/following')
    expect(social.getRelationships).toHaveBeenCalledWith('2', 'following', 1)
    expect(wrapper.findAll('.relationship-row .follow-button')).toHaveLength(1)
    expect(wrapper.get('.relationship-row .follow-button').text()).toBe('已关注')
    expect(wrapper.get('.relationship-copy a').attributes('href')).toBe('/users/3')
    vi.mocked(social.changeFollow).mockRejectedValueOnce(new Error('网络中断'))
    await wrapper.get('.relationship-row .follow-button').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('网络中断')
    vi.mocked(social.changeFollow).mockResolvedValue({ isFollowing: false, followerCount: 0, followingCount: 0 })
    await wrapper.get('.relationship-row .follow-button').trigger('click'); await flushPromises()
    expect(social.changeFollow).toHaveBeenLastCalledWith('3', false)
    expect(social.getRelationships).toHaveBeenCalledTimes(2)
    await router.push('/users/2/followers'); await flushPromises()
    expect(social.getRelationships).toHaveBeenLastCalledWith('2', 'followers', 1)
    wrapper.unmount()
  })
  it('切换关系列表后迟到结果不能写入新列表', async () => {
    vi.mocked(social.getPublicProfile).mockImplementation(async id => profile(id))
    let finish!: (value: Awaited<ReturnType<typeof social.getRelationships>>) => void
    vi.mocked(social.getRelationships).mockReturnValueOnce(new Promise(done => { finish = done })).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 12 })
    const { wrapper, router } = await home('/users/2/following')
    await router.push('/users/3/followers'); await flushPromises()
    finish({ items: [{ id: '9', username: 'late', nickname: '迟到的旧成员', avatarUrl: null, bio: '', isFollowing: true, canFollow: true }], total: 1, page: 1, pageSize: 12 }); await flushPromises()
    expect(wrapper.text()).not.toContain('迟到的旧成员')
    expect(wrapper.get('.profile-works-panel h1').text()).toContain('作者3')
    wrapper.unmount()
  })
  it('关注失败保持状态并允许重试，成功只更新按钮与计数', async () => {
    vi.mocked(social.getPublicProfile).mockResolvedValue(profile())
    vi.mocked(social.changeFollow).mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce({ isFollowing: true, followerCount: 1, followingCount: 0 })
    const { wrapper } = await home()
    await wrapper.get('.follow-button').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('网络中断')
    expect(wrapper.get('.follow-button').attributes('aria-pressed')).toBe('false')
    await wrapper.get('.follow-button').trigger('click'); await flushPromises()
    expect(wrapper.get('.follow-button').text()).toBe('已关注')
    expect(wrapper.get('.follow-counts').text()).toContain('1 位关注者')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('切换作者后迟到的关注结果不能覆盖新作者', async () => {
    let resolve!: (value: social.FollowState) => void
    vi.mocked(social.getPublicProfile).mockImplementation(async id => profile(id))
    vi.mocked(social.changeFollow).mockReturnValue(new Promise(done => { resolve = done }))
    const { wrapper, router } = await home()
    await wrapper.get('.follow-button').trigger('click')
    await router.push('/users/3'); await flushPromises()
    resolve({ isFollowing: true, followerCount: 88, followingCount: 0 }); await flushPromises()
    expect(wrapper.get('h1').text()).toBe('作者3')
    expect(wrapper.get('.follow-button').text()).toBe('关注作者')
    expect(wrapper.text()).not.toContain('88')
    wrapper.unmount()
  })
  it('退出账号后迟到动态不能重新展示', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof social.getActivities>>) => void
    vi.mocked(social.getPublicProfile).mockResolvedValue(profile())
    vi.mocked(social.getActivities).mockReturnValue(new Promise(done => { resolve = done }))
    const { wrapper } = await home('/users/2?tab=activity')
    useAuthStore().clear(); await flushPromises()
    resolve({ items: [{ id: '9', actorId: '2', nickname: '旧作者', avatarUrl: null, activityType: 'checkin', occurredOn: '2026-11-03', createdAt: '2026-11-03T00:00:00Z', routeCount: 1, roadmapId: '10', title: '迟到的动态' }], total: 1, page: 1, pageSize: 12 }); await flushPromises()
    expect(wrapper.text()).not.toContain('迟到的动态')
    expect(wrapper.find('.public-user-profile').exists()).toBe(false)
    wrapper.unmount()
  })
  it('本人左侧访问私人收藏和学习，主页不展示提问或回复', async () => {
    vi.mocked(social.getPublicProfile).mockResolvedValue({ ...profile('1'), canFollow: false })
    const { wrapper } = await home('/profile')
    expect(wrapper.text()).not.toContain('我的提问')
    expect(wrapper.text()).not.toContain('我的回复')
    expect(wrapper.text()).not.toContain('关注动态')
    expect(wrapper.findAll('.profile-public-counts a').map(item => item.attributes('href'))).toEqual(['/users/1/routes', '/favorites', '/learning'])
    expect(wrapper.find('.privacy-entry').exists()).toBe(true)
    expect(wrapper.find('.follow-button').exists()).toBe(false)
    wrapper.unmount()
  })

})

describe('受限讨论Markdown', () => {
  it('原始HTML与脚本仅作为转义文本显示', () => {
    const raw = '<img src=x onerror="alert(1)"><script>alert(1)</script>'
    const wrapper = mount(DiscussionBody, { props: { text: raw } })
    expect(wrapper.findAll('img,script')).toHaveLength(0)
    expect(wrapper.text()).toBe(raw)
  })
  it('仅渲染安全链接、粗体和行内代码', () => {
    const wrapper = mount(DiscussionBody, { props: { text: '**替代资源** `python` [教程](https://example.com/new)' } })
    expect(wrapper.get('strong').text()).toBe('替代资源')
    expect(wrapper.get('code').text()).toBe('python')
    expect(wrapper.get('a').attributes('href')).toBe('https://example.com/new')
    expect(wrapper.get('a').attributes('rel')).toContain('noopener')
  })
  it.each(['javascript:alert(1)', 'data:text/html,a', '//example.com', 'https://name:secret@example.com', 'https://example.com/\nscript'])('拒绝危险或含凭证URL %s', value => {
    expect(safeDiscussionUrl(value)).toBeNull()
  })
  it('危险链接保留可见原文而不生成a标签', () => {
    expect(discussionTokens('[危险](javascript:alert)')).toEqual([{ kind: 'text', text: '[危险](javascript:alert)' }])
  })
})
