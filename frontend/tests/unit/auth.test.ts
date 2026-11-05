import { createPinia, getActivePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../src/api/auth'
import * as userApi from '../../src/api/user'
import { getAccessToken, handleUnauthorized, setAccessToken } from '../../src/api/session'
import { useAuthStore } from '../../src/stores/auth'
import { installAuthGuards, installCommunityGuards } from '../../src/router/guards'
import { createMemoryHistory, createRouter } from 'vue-router'
import { flushPromises, mount } from '@vue/test-utils'
import LoginView from '../../src/views/auth/LoginView.vue'
import ProfileView from '../../src/views/personal/ProfileView.vue'
import type { UserPublic } from '../../src/types/user'
import { ApiError } from '../../src/api/http'
import { ElMessage } from 'element-plus'

vi.mock('element-plus', async importOriginal => ({ ...await importOriginal<typeof import('element-plus')>(), ElMessage: Object.assign(vi.fn(), { closeAll: vi.fn() }) }))

vi.mock('../../src/api/auth', () => ({ login: vi.fn(), logout: vi.fn() }))
vi.mock('../../src/api/user', () => ({ getMe: vi.fn(), getPrivacy: vi.fn(), updatePrivacy: vi.fn(), updateMe: vi.fn(), uploadAvatar: vi.fn(), adminAccounts: vi.fn(), setAccountStatus: vi.fn(), changePassword: vi.fn(), createAccount: vi.fn(), editAccount: vi.fn(), resetAccountPassword: vi.fn() }))
const user: UserPublic = { id: '9223372036854775807', username: 'test_user', nickname: '测试用户', role: 'user', status: 'active', createdAt: '2026-10-29T00:00:00Z' }
beforeEach(() => { vi.mocked(ElMessage).mockClear(); setActivePinia(createPinia()); setAccessToken(null); vi.useFakeTimers() })
afterEach(() => { useAuthStore().clear(); vi.useRealTimers() })

async function login(token = 'token-1') {
  vi.mocked(api.login).mockResolvedValue({ accessToken: token, tokenType: 'bearer', expiresIn: 7200, user })
  const auth = useAuthStore()
  await auth.login({ username: 'test_user', password: 'password-test-123' })
  return auth
}

describe('内存会话边界', () => {
  it('账号切换后迟到的头像上传不能覆盖当前账号', async () => {
    const auth = await login('old-token')
    let finish!: (value: UserPublic) => void
    vi.mocked(userApi.uploadAvatar).mockReturnValueOnce(new Promise(done => { finish = done }))
    const pending = auth.uploadAvatar(new File(['image'], 'avatar.png'))
    await login('new-token')
    finish({ ...user, avatarUrl: '/api/v1/users/avatars/' + 'a'.repeat(32) + '.png' })
    await expect(pending).rejects.toThrow('账号已切换')
    expect(auth.user?.avatarUrl).toBeUndefined()
  })
  it('迟到的登录响应不能覆盖随后完成的新登录', async () => {
    let finishOld!: (value: Awaited<ReturnType<typeof api.login>>) => void
    vi.mocked(api.login).mockReturnValueOnce(new Promise(done => { finishOld = done }))
    const auth = useAuthStore()
    const pending = auth.login({ username: 'old_user', password: 'abcdef' })
    await login('current-token')
    finishOld({ accessToken: 'old-token', tokenType: 'bearer', expiresIn: 7200, user })
    expect(await pending).toBe(false)
    expect(getAccessToken()).toBe('current-token')
  })

  it('旧会话退出的迟到响应不能清除新登录', async () => {
    const auth = await login('old-token')
    let finish!: () => void
    vi.mocked(api.logout).mockReturnValueOnce(new Promise(done => { finish = done }))
    const pending = auth.logout()
    await login('new-token')
    finish()
    await pending
    expect(getAccessToken()).toBe('new-token')
    expect(auth.authenticated).toBe(true)
  })
  it('到期自动清理，未持久化到浏览器存储', async () => {
    const auth = await login()
    expect(auth.authenticated).toBe(true)
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    await vi.advanceTimersByTimeAsync(7200 * 1000)
    expect(auth.authenticated).toBe(false)
    expect(getAccessToken()).toBeNull()
  })

  it('旧请求的 401 不影响新会话，当前凭证失效才清理', async () => {
    const auth = await login('new-token')
    handleUnauthorized('Bearer old-token')
    expect(auth.authenticated).toBe(true)
    handleUnauthorized('Bearer new-token')
    expect(auth.authenticated).toBe(false)
  })

  it('退出成功才清理，并区分主动退出和到期', async () => {
    const auth = await login()
    vi.mocked(api.logout).mockRejectedValueOnce(new Error('网络失败'))
    await expect(auth.logout()).rejects.toThrow('网络失败')
    expect(auth.authenticated).toBe(true)
    vi.mocked(api.logout).mockResolvedValueOnce(undefined)
    await auth.logout()
    expect(auth.authenticated).toBe(false)
    expect(auth.endReason).toBe('logout')
  })

  it('退出后迟到的资料响应不能恢复身份', async () => {
    const auth = await login()
    let resolve!: (user: UserPublic) => void
    vi.mocked(userApi.getMe).mockReturnValue(new Promise(done => { resolve = done }))
    const pending = auth.refreshProfile()
    auth.clear()
    resolve(user)
    await expect(pending).rejects.toThrow('账号已切换')
    expect(auth.user).toBeNull()
    expect(getAccessToken()).toBeNull()
  })
})

describe('本人隐私设置', () => {
  const settings = { topicPublic: false, publishPublic: true, checkinPublic: false, favoritePublic: false, learningPublic: false, settingsVersion: 1 }
  async function setupSettings(section = 'profile') {
    await login()
    vi.mocked(userApi.getMe).mockResolvedValue({ ...user })
    vi.mocked(userApi.getPrivacy).mockResolvedValue({ ...settings })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/settings', name: 'settings', component: ProfileView },
      { path: '/profile', component: { template: '<div />' } },
    ] })
    await router.push('/settings?section=' + section)
    const wrapper = mount(ProfileView, { global: { plugins: [router], stubs: { ElTag: true, ElButton: true } } })
    await flushPromises()
    return wrapper
  }
  it('侧栏一次只展示一个表单，切换后清空密码和迟到的隐私结果', async () => {
    const wrapper = await setupSettings()
    const router = wrapper.vm.$router
    expect(wrapper.findAll('.profile-card')).toHaveLength(1)
    expect(wrapper.find('#old-password').exists()).toBe(false)
    expect(wrapper.find('form[aria-label="隐私设置"]').exists()).toBe(false)
    await router.push('/settings?section=password'); await flushPromises()
    await wrapper.get('#old-password').setValue('unsubmitted-password')
    expect(wrapper.find('#profile-nickname').exists()).toBe(false)
    await router.push('/settings?section=profile'); await flushPromises()
    await router.push('/settings?section=password'); await flushPromises()
    expect((wrapper.get('#old-password').element as HTMLInputElement).value).toBe('')
    let finish!: (value: typeof settings) => void
    vi.mocked(userApi.getPrivacy).mockReturnValueOnce(new Promise(done => { finish = done }))
    await router.push('/settings?section=privacy'); await flushPromises()
    await router.push('/settings?section=profile'); await flushPromises()
    finish({ ...settings, favoritePublic: true }); await flushPromises()
    expect(wrapper.find('form[aria-label="隐私设置"]').exists()).toBe(false)
    expect(wrapper.find('#profile-nickname').exists()).toBe(true)
    wrapper.unmount()
  })
  it('默认头像不要求地址，上传保留未保存资料，失败保留当前头像', async () => {
    const wrapper = await setupSettings()
    expect(wrapper.find('#profile-avatar').exists()).toBe(false)
    expect(wrapper.find('.identity-panel svg').exists()).toBe(true)
    await wrapper.get('#profile-nickname').setValue('尚未保存的昵称')
    await wrapper.get('#profile-bio').setValue('尚未保存的简介')
    const input = wrapper.get('input[type="file"]')
    const file = new File(['image'], 'avatar.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    const url = '/api/v1/users/avatars/' + 'a'.repeat(32) + '.png'
    vi.mocked(userApi.uploadAvatar).mockResolvedValueOnce({ ...user, avatarUrl: url })
    await input.trigger('change')
    await flushPromises()
    expect(wrapper.get('.identity-panel img').attributes('src')).toBe(url)
    expect((wrapper.get('#profile-nickname').element as HTMLInputElement).value).toBe('尚未保存的昵称')
    expect((wrapper.get('#profile-bio').element as HTMLTextAreaElement).value).toBe('尚未保存的简介')
    vi.mocked(userApi.uploadAvatar).mockRejectedValueOnce(new Error('请选择有效图片'))
    await input.trigger('change')
    await flushPromises()
    expect(wrapper.text()).toContain('请选择有效图片')
    expect(wrapper.get('.identity-panel img').attributes('src')).toBe(url)
    Object.defineProperty(input.element, 'files', { value: [], configurable: true })
    await input.trigger('change')
    expect(userApi.uploadAvatar).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
  it('按五类独立显示，保存携带当前版本', async () => {
    const wrapper = await setupSettings('privacy')
    const form = wrapper.get('form[aria-label="隐私设置"]')
    const inputs = form.findAll('input')
    expect(inputs.map(input => (input.element as HTMLInputElement).checked)).toEqual([true, false, false, false, false])
    await inputs[2]!.setValue(true)
    vi.mocked(userApi.updatePrivacy).mockResolvedValue({ ...settings, checkinPublic: true, settingsVersion: 2 })
    await form.trigger('submit')
    await flushPromises()
    expect(userApi.updatePrivacy).toHaveBeenCalledWith({ ...settings, checkinPublic: true })
    expect(ElMessage).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('隐私设置已保存'), duration: 3000, showClose: true }))
    wrapper.unmount()
  })
  it('同账号资料响应是新对象时不会重复加载设置', async () => {
    const wrapper = await setupSettings()
    expect(userApi.getMe).toHaveBeenCalledTimes(1)
    expect(userApi.getPrivacy).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('409后重新加载服务端设置并要求再次确认', async () => {
    const wrapper = await setupSettings('privacy')
    vi.mocked(userApi.updatePrivacy).mockRejectedValue(new ApiError('版本冲突', 409, 'PRIVACY_VERSION_CONFLICT'))
    vi.mocked(userApi.getPrivacy).mockResolvedValue({ ...settings, learningPublic: true, settingsVersion: 2 })
    await wrapper.get('form[aria-label="隐私设置"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('请检查后再保存')
    expect((wrapper.get('input[aria-label="学习列表"]').element as HTMLInputElement).checked).toBe(true)
    wrapper.unmount()
  })
  it('切换账号后立即清空私有表单，迟到隐私响应不能回填', async () => {
    const wrapper = await setupSettings('privacy')
    let finish!: (value: typeof settings) => void
    vi.mocked(userApi.updatePrivacy).mockReturnValueOnce(new Promise(done => { finish = done }))
    await wrapper.get('form[aria-label="隐私设置"]').trigger('submit')
    useAuthStore().clear()
    await flushPromises()
    finish({ ...settings, favoritePublic: true })
    await flushPromises()
    expect(wrapper.find('form[aria-label="隐私设置"]').exists()).toBe(false)
    expect(wrapper.find('#profile-nickname').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('固定登录落点', () => {
  it.each([
    ['user', '/settings'], ['user', '/admin/reports'], ['user', 'https://example.com'], ['user', undefined],
    ['admin', '/settings'], ['admin', '/admin/reports'], ['admin', 'https://example.com'], ['admin', undefined],
  ] as const)('%s 登录忽略旧回跳目标 %s', async (role, redirect) => {
    vi.mocked(api.login).mockResolvedValue({ accessToken: 'fixed-login', tokenType: 'bearer', expiresIn: 7200, user: { ...user, role } })
    const component = { template: '<p>目标页面</p>' }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/login', name: 'login', component: LoginView },
      { path: '/register', name: 'register', component },
      { path: '/', name: 'community', component },
      { path: '/admin/roadmaps', name: 'admin-roadmaps', component, meta: { requiresAuth: true, requiresAdmin: true } },
      { path: '/settings', name: 'settings', component, meta: { requiresAuth: true } },
      { path: '/admin/reports', name: 'admin-reports', component, meta: { requiresAuth: true, requiresAdmin: true } },
      { path: '/forbidden', name: 'forbidden', component },
    ] })
    installAuthGuards(router, getActivePinia()!)
    await router.push({ path: '/login', query: redirect ? { redirect, reason: 'expired' } : {} })
    const wrapper = mount(LoginView, { global: { plugins: [router], stubs: { ElButton: true } } })
    await wrapper.get('#login-username').setValue('test_user')
    await wrapper.get('#login-password').setValue('password-test-123')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(router.currentRoute.value.path).toBe(role === 'admin' ? '/admin/roadmaps' : '/')
    expect(router.currentRoute.value.query).toEqual({})
    wrapper.unmount()
  })
})
describe('社区阶段开放边界', () => {
  it.each(['/', '/login', '/register', '/admin/users', '/roadmaps/1', '/learning/1'])('阻止旧页面挂载：%s', async path => {
    const pinia = createPinia()
    const mounted = vi.fn()
    const component = { mounted, template: '<p>旧业务</p>' }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path, name: 'legacy', component, meta: { requiresAuth: true } },
      { path: '/preparing', name: 'community-pending', component: { template: '<p>社区升级中</p>' } },
      { path: '/environment', name: 'overview', component: { template: '<p>环境</p>' } },
    ] })
    installCommunityGuards(router)
    installAuthGuards(router, pinia)
    await router.push(path)
    const wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [router, pinia] } })
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('community-pending')
    expect(mounted).not.toHaveBeenCalled()
    expect(api.login).not.toHaveBeenCalled()
    await router.push('/environment')
    expect(router.currentRoute.value.name).toBe('overview')
    wrapper.unmount()
  })
})

describe('管理员社区身份和治理权限', () => {
  it('普通用户不能进入账号管理页面', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    await login()
    const component = { template: '<p />' }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/admin/users', name: 'admin-users', component, meta: { requiresAuth: true, requiresAdmin: true } },
      { path: '/forbidden', name: 'forbidden', component },
    ] })
    installAuthGuards(router, pinia)
    await router.push('/admin/users')
    expect(router.currentRoute.value.name).toBe('forbidden')
  })
  it.each(['/','/learning','/favorites','/records','/profile','/login'])('管理员访问 %s 转入独立后台', async path => {
    const pinia = createPinia()
    setActivePinia(pinia)
    vi.mocked(api.login).mockResolvedValue({ accessToken: 'admin-token', tokenType: 'bearer', expiresIn: 7200, user: { ...user, role: 'admin' } })
    await useAuthStore().login({ username: 'admin', password: 'abcdef' })
    const component = { template: '<p />' }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', name: 'community', component },
      { path: '/admin/roadmaps', name: 'admin-roadmaps', component, meta: { requiresAuth: true, requiresAdmin: true } },
      ...['learning','favorites','records','profile'].map(name => ({ path: '/' + name, name, component })),
      { path: '/login', name: 'login', component, meta: { guestOnly: true } },
      { path: '/preparing', name: 'community-pending', component, meta: { requiresAuth: true, requiresAdmin: true } },
    ] })
    installAuthGuards(router, pinia)
    await router.push(path)
    expect(router.currentRoute.value.path).toBe('/admin/roadmaps')
  })
})

describe('账号管理页面', () => {
  async function setupAccounts() {
    const auth = useAuthStore()
    auth.user = { ...user, role: 'admin' }
    const student = { ...user, id: '500', username: 'student' }
    vi.mocked(userApi.adminAccounts).mockResolvedValue({ items: [student, auth.user], total: 2, page: 1, pageSize: 20 })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/admin/users', name: 'admin-users', component: ProfileView },
    ] })
    await router.push('/admin/users')
    const wrapper = mount(ProfileView, { global: { plugins: [router], stubs: {
      ElTag: true, ElButton: true,
      AppDialog: { template: '<section><slot /><slot name="footer" /></section>' },
    } } })
    await flushPromises()
    return { wrapper, student }
  }

  it('支持筛选并保护管理员，取消确认不会禁用账号', async () => {
    const { wrapper } = await setupAccounts()
    expect(wrapper.text()).toContain('管理员保护')
    expect(wrapper.find('.profile-page').exists()).toBe(false)
    await wrapper.get('#account-keyword').setValue('student')
    await wrapper.get('#account-state').setValue('active')
    await flushPromises()
    expect(userApi.adminAccounts).toHaveBeenLastCalledWith({ keyword: 'student', role: undefined, status: 'active', page: 1 })
    await wrapper.findAll('tbody button').find(button => button.text() === '禁用账号')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '取消')!.trigger('click')
    expect(userApi.setAccountStatus).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('确认禁用后调用状态接口并刷新账号列表', async () => {
    const { wrapper, student } = await setupAccounts()
    vi.mocked(userApi.setAccountStatus).mockResolvedValue({ ...student, status: 'disabled' })
    await wrapper.findAll('tbody button').find(button => button.text() === '禁用账号')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '确认')!.trigger('click')
    await flushPromises()
    expect(userApi.setAccountStatus).toHaveBeenCalledWith(student, 'disabled')
    expect(ElMessage).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('账号已禁用'), duration: 3000, showClose: true }))
    expect(userApi.adminAccounts).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it.each(['user', 'admin'] as const)('可以创建%s角色账号，成功后清除密码并刷新列表', async role => {
    const { wrapper, student } = await setupAccounts()
    vi.mocked(userApi.createAccount).mockResolvedValue({ ...student, role })
    await wrapper.findAll('button').find(button => button.text().includes('＋ 创建账号'))!.trigger('click')
    await wrapper.get('#managed-username').setValue('new_account')
    await wrapper.get('#managed-role').setValue(role)
    await wrapper.get('#managed-password').setValue('abcdef')
    await wrapper.get('#managed-confirmation').setValue('abcdef')
    await wrapper.get('#admin-account-form').trigger('submit')
    await flushPromises()
    expect(userApi.createAccount).toHaveBeenCalledWith({ username: 'new_account', nickname: null, password: 'abcdef', role })
    expect(wrapper.find('#managed-password').exists()).toBe(false)
    expect(ElMessage).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('账号已创建'), duration: 3000, showClose: true }))
    expect(userApi.adminAccounts).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('重置前校验两次密码一致，成功后刷新并显示凭证失效提示', async () => {
    const { wrapper, student } = await setupAccounts()
    vi.mocked(userApi.resetAccountPassword).mockResolvedValue(undefined)
    await wrapper.findAll('tbody button').find(button => button.text() === '重置密码')!.trigger('click')
    await wrapper.get('#managed-password').setValue('abcdef')
    await wrapper.get('#managed-confirmation').setValue('different')
    await wrapper.get('#admin-account-form').trigger('submit')
    expect(userApi.resetAccountPassword).not.toHaveBeenCalled()
    await wrapper.get('#managed-confirmation').setValue('abcdef')
    await wrapper.get('#admin-account-form').trigger('submit')
    await flushPromises()
    expect(userApi.resetAccountPassword).toHaveBeenCalledWith(student.id, 'abcdef')
    expect(ElMessage).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('旧登录凭证已失效'), duration: 3000, showClose: true }))
    wrapper.unmount()
  })

  it('昵称保存传入原账号快照，创建失败保持表单供修正', async () => {
    const { wrapper, student } = await setupAccounts()
    vi.mocked(userApi.editAccount).mockResolvedValue({ ...student, nickname: '新昵称' })
    await wrapper.findAll('tbody button').find(button => button.text() === '编辑昵称')!.trigger('click')
    await wrapper.get('#managed-nickname').setValue('新昵称')
    await wrapper.get('#admin-account-form').trigger('submit')
    await flushPromises()
    expect(userApi.editAccount).toHaveBeenCalledWith(student, '新昵称')
    vi.mocked(userApi.createAccount).mockRejectedValue(new Error('该用户名已被使用'))
    await wrapper.findAll('button').find(button => button.text().includes('＋ 创建账号'))!.trigger('click')
    await wrapper.get('#managed-username').setValue('duplicate')
    await wrapper.get('#managed-password').setValue('abcdef')
    await wrapper.get('#managed-confirmation').setValue('abcdef')
    await wrapper.get('#admin-account-form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('该用户名已被使用')
    expect(wrapper.find('#admin-account-form').exists()).toBe(true)
    wrapper.unmount()
  })
})
