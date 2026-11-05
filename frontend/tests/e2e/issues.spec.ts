import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

const backend = fileURLToPath(new URL('../../../backend/', import.meta.url))

test('R09个人主页固定卡片、十条动态、五项隐私与独立列表', async ({ page, browser, request }, testInfo) => {
  test.setTimeout(180000)
  const names = [0, 1, 2].map(() => 'r02_' + randomUUID().replaceAll('-', '').slice(0, 24))
  const password = 'r09-profile-password'
  const context = await browser.newContext({ baseURL: testInfo.project.use.baseURL })
  const ownerPage = await context.newPage()
  const errors: string[] = []
  for (const target of [page, ownerPage]) target.on('pageerror', error => errors.push(error.message))
  async function login(target: Page, index: number, path: string) {
    await target.goto('/login?redirect=' + encodeURIComponent(path))
    await target.getByLabel('用户名', { exact: true }).fill(names[index]!)
    await target.getByLabel('密码', { exact: true }).fill(password)
    await target.getByRole('button', { name: '登录', exact: true }).click()
    await expect(target).toHaveURL(/\/$/)
    await target.evaluate(target => {
      history.pushState(null, '', target)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, path)
    await expect.poll(() => new URL(target.url()).pathname).toBe(path)
  }
  try {
    const ids: string[] = [], tokens: string[] = []
    for (const [index, username] of names.entries()) {
      const response = await request.post('/api/v1/auth/register', { data: { username, password, nickname: ['林间拾光', '学习分享者', '关注者'][index] } })
      expect(response.status()).toBe(201); ids.push((await response.json()).data.id as string)
      tokens.push((await (await request.post('/api/v1/auth/login', { data: { username, password } })).json()).data.accessToken as string)
    }
    const owner = { Authorization: 'Bearer ' + tokens[0] }, actor = { Authorization: 'Bearer ' + tokens[1] }, viewer = { Authorization: 'Bearer ' + tokens[2] }
    await request.patch('/api/v1/users/me', { headers: owner, data: { bio: '热爱学习，也喜欢把走过的路分享给你。' } })
    async function publishRoute(title: string, headers: Record<string, string>) {
      const rid = (await (await request.post('/api/v1/roadmaps', { headers, data: { title } })).json()).data.id as string
      const doc = (await (await request.put('/api/v1/roadmaps/' + rid + '/draft', { headers, data: {
        expectedVersion: 1, title, description: '从基础知识到项目实践，循序渐进建立系统的学习路径。', connections: [],
        stages: [{ id: 'tmp_s', title: '基础入门', nodes: [{ id: 'tmp_n', title: '动手实践', content: 'PRIVATE_PROFILE_BODY', resources: [{ id: 'tmp_r', title: '官方教程', resourceType: 'article', resourceUrl: 'https://example.com/learn' }] }] }],
      } })).json()).data.document
      const released = (await (await request.post('/api/v1/roadmaps/' + rid + '/publish', { headers, data: { expectedVersion: doc.expectedVersion, updateSummary: '首次发布' } })).json()).data.releaseId as string
      return { rid, doc, released }
    }
    const routes = []
    for (const title of ['学习方法基础', 'LangGraph 智能体开发', '数据库设计基础', 'Vue 3 前端进阶', 'Python 从入门到实践']) routes.push(await publishRoute(title, owner))
    const first = routes[0]!
    const topicIds: string[] = []
    for (const title of ['如何安排练习顺序？', '有哪些推荐的实践资料？', '怎样验证学习效果？', '项目练习需要哪些基础？', '学习过程中如何复习？', '如何整理自己的知识体系？']) {
      const result = await request.post('/api/v1/roadmaps/' + first.rid + '/issues', { headers: owner, data: { title, body: '讨论路线的学习与实践方法。' } })
      expect(result.status()).toBe(201); topicIds.push((await result.json()).data.id as string)
    }
    const other = await publishRoute('后端工程实践', actor)
    const relation = (await (await request.post('/api/v1/roadmaps/' + other.rid + '/enroll', { headers: owner, data: { releaseId: other.released } })).json()).data
    expect((await request.put('/api/v1/roadmaps/' + other.rid + '/favorite', { headers: owner })).status()).toBe(200)
    expect((await request.post('/api/v1/enrollments/' + relation.id + '/records', { headers: owner, data: { sessionId: relation.sessionId } })).status()).toBe(200)
    expect((await request.post('/api/v1/roadmaps/' + first.rid + '/issues/' + topicIds[0] + '/comments', { headers: owner, data: { body: 'PRIVATE_REPLY_NOT_IN_PROFILE' } })).status()).toBe(201)

    await login(page, 2, '/users/' + ids[0])
    await expect(page.locator('.profile-route-card')).toHaveCount(4)
    await expect(page.locator('.profile-route-card').first()).toContainText('Python 从入门到实践')
    await expect(page.locator('.profile-tabs')).toHaveCount(0)
    await expect(page.locator('.activity-row')).toHaveCount(5)
    await expect(page.locator('.profile-public-counts')).toContainText('发布路线5')
    await expect(page.locator('.profile-public-counts a').filter({ hasText: '个人收藏' })).toHaveCount(0)
    await expect(page.locator('.public-user-profile')).not.toContainText('PRIVATE_PROFILE_BODY')
    await expect(page.locator('.public-user-profile')).not.toContainText('PRIVATE_REPLY_NOT_IN_PROFILE')
    await expect(page.getByText('我的提问', { exact: true })).toHaveCount(0)
    await expect(page.getByText('我的回复', { exact: true })).toHaveCount(0)
    await expect(page.locator('.message-link svg')).toBeVisible()
    await expect(page.locator('.message-badge')).toHaveCount(0)
    await page.getByRole('button', { name: '关注作者', exact: true }).click()
    await expect(page.getByRole('button', { name: '已关注', exact: true })).toBeVisible()
    const cards = await page.locator('.profile-route-card').evaluateAll(items => items.map(item => ({ x: item.getBoundingClientRect().x, y: item.getBoundingClientRect().y })))
    expect(cards[0]!.y).toBe(cards[1]!.y); expect(cards[2]!.y).toBe(cards[3]!.y); expect(cards[2]!.y).toBeGreaterThan(cards[0]!.y)

    // 三方关系用于校验列表按钮以查看者而非主页作者为准。
    expect((await request.put('/api/v1/users/' + ids[1] + '/follow', { headers: owner })).status()).toBe(200)
    expect((await request.put('/api/v1/users/' + ids[1] + '/follow', { headers: viewer })).status()).toBe(200)
    expect((await request.put('/api/v1/users/' + ids[0] + '/follow', { headers: actor })).status()).toBe(200)
    await page.getByRole('button', { name: '刷新动态', exact: true }).click()
    await page.locator('.follow-counts a').filter({ hasText: '人关注中' }).click()
    await expect(page.locator('.relationship-row')).toHaveCount(1)
    await expect(page.locator('.relationship-row .follow-button')).toHaveText('已关注')
    await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo(0, 0) }); await page.mouse.move(8, 8)
    await page.screenshot({ path: testInfo.outputPath('profile-following-desktop.png'), fullPage: true })
    await page.locator('.relationship-row .follow-button').click()
    await expect(page.locator('.relationship-row .follow-button')).toHaveText('关注')
    await page.getByRole('navigation', { name: '关注列表分类' }).getByRole('link', { name: /关注者/ }).click()
    await expect(page.locator('.relationship-row')).toHaveCount(2)
    await expect(page.locator('.relationship-row .follow-button')).toHaveCount(1)
    await expect(page.locator('.relationship-row').filter({ hasText: '我自己' })).toHaveCount(1)
    await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo(0, 0) }); await page.mouse.move(8, 8)
    await page.screenshot({ path: testInfo.outputPath('profile-followers-desktop.png'), fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo(0, 0) }); await page.mouse.move(8, 8)
    await page.screenshot({ path: testInfo.outputPath('profile-followers-mobile.png'), fullPage: true })
    await page.locator('.relationship-row').filter({ hasText: '学习分享者' }).getByRole('link', { name: '查看学习分享者的个人主页' }).click()
    await expect.poll(() => new URL(page.url()).pathname).toBe('/users/' + ids[1])
    await page.locator('.follow-counts a').filter({ hasText: '位关注者' }).click()
    await page.locator('.relationship-copy a').filter({ hasText: '林间拾光' }).click()
    await expect.poll(() => new URL(page.url()).pathname).toBe('/users/' + ids[0])
    await page.setViewportSize({ width: 1440, height: 1000 })

    await login(ownerPage, 0, '/profile')
    await expect(ownerPage.locator('.activity-row')).toHaveCount(10)
    await expect(ownerPage.locator('.profile-public-counts')).toContainText('个人收藏1')
    await expect(ownerPage.locator('.profile-public-counts')).toContainText('个人学习1')
    await ownerPage.getByRole('button', { name: '隐私设置', exact: true }).click()
    const dialog = ownerPage.getByRole('dialog', { name: '隐私设置', exact: true })
    await expect(dialog.getByRole('switch')).toHaveCount(5)
    await expect(dialog.getByRole('switch', { name: '发布话题动态', exact: true })).not.toBeChecked()
    for (const label of ['发布话题动态', '打卡动态', '收藏列表', '学习列表']) await dialog.getByRole('switch', { name: label, exact: true }).check()
    await ownerPage.screenshot({ path: testInfo.outputPath('profile-privacy-desktop.png') })
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    expect((await (await request.get('/api/v1/users/me/privacy', { headers: owner })).json()).data.topicPublic).toBe(false)
    await ownerPage.getByRole('button', { name: '隐私设置', exact: true }).click()
    for (const label of ['发布话题动态', '打卡动态', '收藏列表', '学习列表']) await dialog.getByRole('switch', { name: label, exact: true }).check()
    await dialog.getByRole('button', { name: '保存设置', exact: true }).click()
    await expect(dialog).toHaveCount(0)
    await page.getByRole('button', { name: '刷新动态', exact: true }).click()
    await expect(page.locator('.activity-row')).toHaveCount(10)
    await expect(page.locator('.profile-public-counts')).toContainText('个人收藏1')
    await expect(page.locator('.profile-public-counts')).toContainText('个人学习1')
    await expect(page.locator('.profile-timeline')).toContainText('发布了话题')
    await expect(page.locator('.profile-timeline')).toContainText('发布了路线')
    await expect(page.locator('.profile-timeline')).toContainText('学习打卡')
    await page.evaluate(() => window.scrollTo(0, 0)); await page.mouse.move(8, 8)
    await page.screenshot({ path: testInfo.outputPath('profile-fixed-desktop.png'), fullPage: true })
    await page.getByRole('link', { name: /发布路线/ }).click()
    await expect(page.locator('.profile-list-page .profile-route-card')).toHaveCount(5)
    await page.getByRole('link', { name: '返回个人主页', exact: true }).click()
    await page.getByRole('link', { name: /个人收藏/ }).click()
    await expect(page.locator('.profile-list-page')).toContainText('后端工程实践')
    await page.getByRole('link', { name: '返回个人主页', exact: true }).click()
    await page.getByRole('link', { name: /个人学习/ }).click()
    await expect(page.locator('.profile-list-page')).toContainText('后端工程实践')
    await page.getByRole('link', { name: '返回个人主页', exact: true }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.locator('.profile-route-card')).toHaveCount(4)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.evaluate(() => window.scrollTo(0, 0)); await page.mouse.move(8, 8)
    await page.screenshot({ path: testInfo.outputPath('profile-fixed-mobile.png'), fullPage: true })
    await ownerPage.setViewportSize({ width: 390, height: 844 })
    await ownerPage.getByRole('button', { name: '隐私设置', exact: true }).click()
    await expect(dialog.getByRole('switch')).toHaveCount(5)
    const saveBounds = await dialog.getByRole('button', { name: '保存设置', exact: true }).boundingBox()
    expect(saveBounds && saveBounds.y >= 0 && saveBounds.y + saveBounds.height <= 844).toBeTruthy()
    await ownerPage.screenshot({ path: testInfo.outputPath('profile-privacy-mobile.png') })
    for (const label of ['发布话题动态', '打卡动态', '收藏列表', '学习列表']) await dialog.getByRole('switch', { name: label, exact: true }).uncheck()
    await dialog.getByRole('button', { name: '保存设置', exact: true }).click()
    await expect(dialog).toHaveCount(0)
    await page.getByRole('button', { name: '刷新动态', exact: true }).click()
    await expect(page.locator('.activity-row')).toHaveCount(5)
    await expect(page.locator('.profile-public-counts a').filter({ hasText: '个人收藏' })).toHaveCount(0)
    await expect(page.locator('.profile-public-counts a').filter({ hasText: '个人学习' })).toHaveCount(0)

    await login(page, 2, '/roadmaps/' + first.rid)
    await page.getByRole('button', { name: '订阅更新', exact: true }).click()
    first.doc.stages[0].nodes[0].content = 'PRIVATE_PROFILE_V2'
    first.doc = (await (await request.put('/api/v1/roadmaps/' + first.rid + '/draft', { headers: owner, data: first.doc })).json()).data.document
    expect((await request.post('/api/v1/roadmaps/' + first.rid + '/publish', { headers: owner, data: { expectedVersion: first.doc.expectedVersion, updateSummary: '补充练习' } })).status()).toBe(200)
    await expect.poll(async () => (await (await request.get('/api/v1/notifications', { headers: viewer })).json()).data.total).toBe(1)
    await page.getByRole('link', { name: /^消息/ }).click()
    await expect(page.locator('.message-badge')).toHaveText('1')
    await expect(page.locator('.message-card')).toHaveCount(1)
    expect(errors).toEqual([])
  } finally {
    await context.close()
    const cleanup = [
      'import asyncio,sys', 'from app.config.settings import Settings', 'from app.database.session import Database',
      'from tests.route_cleanup import cleanup_routes', 'from tests.integration.test_accounts import cleanup_accounts',
      'async def main():', ' db=Database(Settings().for_community_tests())', ' try:',
      '  await cleanup_routes(db,set(sys.argv[1:]))', '  await cleanup_accounts(db,set(sys.argv[1:]))',
      ' finally: await db.close()', "if sys.platform=='win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())", 'asyncio.run(main())',
    ].join('\n')
    execFileSync('uv', ['run', 'python', '-c', cleanup, ...names], { cwd: backend, env: { ...process.env, PYTHONUTF8: '1' }, stdio: 'pipe' })
  }
})

test('R07失效反馈、作者通知、发布替代、回复解决及主动升级独立', async ({ page, browser, request }, testInfo) => {
  test.setTimeout(180000)
  const names = [0, 1, 2].map(() => 'r02_' + randomUUID().replaceAll('-', '').slice(0, 24))
  const password = 'r07-browser-password'
  const ownerContext = await browser.newContext({ baseURL: testInfo.project.use.baseURL })
  const ownerPage = await ownerContext.newPage()
  const thirdContext = await browser.newContext({ baseURL: testInfo.project.use.baseURL })
  const thirdPage = await thirdContext.newPage()
  const errors: string[] = []
  for (const p of [page, ownerPage, thirdPage]) p.on('pageerror', e => errors.push(e.message))
  async function login(p: Page, username: string, path: string) {
    await p.goto('/login?redirect=' + encodeURIComponent(path))
    await p.getByLabel('用户名', { exact: true }).fill(username)
    await p.getByLabel('密码', { exact: true }).fill(password)
    await p.getByRole('button', { name: '登录', exact: true }).click()
    await expect(p).toHaveURL(/\/$/)
    await p.evaluate(target => {
      history.pushState(null, '', target)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, path)
    await expect(p).toHaveURL(new RegExp(path.replaceAll('/', '\\/') + '$'))
  }
  try {
    for (const [index, username] of names.entries()) expect((await request.post('/api/v1/auth/register', { data: { username, password, nickname: ['路线创作者', '学习探索者', '讨论参与者'][index] } })).status()).toBe(201)
    const tokens: string[] = []
    for (const username of names) tokens.push((await (await request.post('/api/v1/auth/login', { data: { username, password } })).json()).data.accessToken as string)
    const owner = { Authorization: 'Bearer ' + tokens[0] }, reader = { Authorization: 'Bearer ' + tokens[1] }
    const rid = (await (await request.post('/api/v1/roadmaps', { headers: owner, data: { title: 'Python资源反馈路线' } })).json()).data.id as string
    let doc = (await (await request.put('/api/v1/roadmaps/' + rid + '/draft', { headers: owner, data: {
      expectedVersion: 1, title: 'Python资源反馈路线', description: '面向初学者，学习变量与类型。', licenseCode: 'UNLICENSED', connections: [],
      stages: [{ id: 'tmp_s', title: '基础入门', nodes: [{ id: 'tmp_n', title: '变量', content: 'PRIVATE_R07_BODY', resources: [{ id: 'tmp_r', title: '视频', resourceType: 'video', resourceUrl: 'https://example.com/old' }] }] }],
    } })).json()).data.document
    const originalRelease = (await (await request.post('/api/v1/roadmaps/' + rid + '/publish', { headers: owner, data: { expectedVersion: doc.expectedVersion, updateSummary: '首次发布' } })).json()).data.releaseId as string
    const relation = (await (await request.post('/api/v1/roadmaps/' + rid + '/enroll', { headers: reader, data: { releaseId: originalRelease } })).json()).data
    await page.goto('/roadmaps/' + rid)
    await page.getByRole('link', { name: '问题与反馈', exact: true }).click()
    await expect(page).toHaveURL(/\/login$/)
    await page.getByLabel('用户名', { exact: true }).fill(names[1]!)
    await page.getByLabel('密码', { exact: true }).fill(password)
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    await page.evaluate(target => {
      history.pushState(null, '', target)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, '/roadmaps/' + rid + '/issues')
    await expect(page.getByRole('heading', { name: '问题与反馈', exact: true })).toBeVisible()
    await expect(page.locator('.topic-statistics')).toContainText('0')
    await expect(page.locator('.discussion-page')).not.toContainText('围绕路线交流问题与建议')
    await page.getByRole('button', { name: '新建话题', exact: true }).click()
    await page.getByLabel('话题标题', { exact: true }).fill('第三阶段视频链接失效，有替代资源吗？')
    await page.getByLabel('话题正文', { exact: true }).fill('视频无法打开。<img src=x onerror="window.r07xss=true">')
    await page.getByRole('button', { name: '提交话题', exact: true }).click()
    await expect(page).toHaveURL(/\/issues\/\d+$/)
    const topicPath = new URL(page.url()).pathname
    await expect(page.locator('.discussion-body').first()).toContainText('<img')
    expect(await page.evaluate(() => (window as unknown as { r07xss?: boolean }).r07xss)).toBeUndefined()
    expect(await page.locator('.discussion-body img').count()).toBe(0)
    await expect(page.locator('.discussion-page')).not.toContainText('PRIVATE_R07_BODY')
    await page.getByRole('button', { name: '编辑话题', exact: true }).click()
    await page.getByLabel('话题正文', { exact: true }).fill('在学习第三阶段的视频时，第二个链接已经无法打开。\n\n希望能补充一个可访问的替代资源，或者说明推荐的学习顺序。\n\n**资源位置**：第三阶段 / 第四节点 / 第二个视频。')
    await page.getByRole('button', { name: '提交话题', exact: true }).click()
    await expect(page.locator('.topic-content strong')).toHaveText('资源位置')
    await login(ownerPage, names[0]!, '/notifications')
    await expect(async () => {
      await ownerPage.getByRole('button', { name: '刷新消息', exact: true }).click()
      await expect(ownerPage.locator('.message-card')).toContainText('你的路线收到了新话题')
    }).toPass({ timeout: 15000 })
    await ownerPage.getByRole('button', { name: '查看消息', exact: true }).click()
    await expect(ownerPage).toHaveURL(new RegExp(topicPath + '$'))
    doc.stages[0].nodes[0].resources[0].resourceUrl = 'https://example.com/replacement'
    doc = (await (await request.put('/api/v1/roadmaps/' + rid + '/draft', { headers: owner, data: doc })).json()).data.document
    expect((await request.post('/api/v1/roadmaps/' + rid + '/publish', { headers: owner, data: { expectedVersion: doc.expectedVersion, updateSummary: '替换失效视频' } })).status()).toBe(200)
    await ownerPage.getByLabel('回复正文', { exact: true }).fill('原链接已下架，已更新替代链接。')
    await ownerPage.getByRole('button', { name: '发送回复', exact: true }).click()
    await expect(ownerPage.locator('.comment-thread')).toContainText('已更新替代链接')
    await ownerPage.getByLabel('目标状态', { exact: true }).selectOption('resolved')
    await ownerPage.getByRole('button', { name: '保存状态', exact: true }).click()
    await expect(ownerPage.locator('.issue-status').first()).toHaveText('已处理')
    await ownerPage.getByRole('tab', { name: '时间线', exact: true }).click()
    await expect(ownerPage.locator('.sidebar-timeline')).toContainText('标记已处理')
    await ownerPage.screenshot({ path: testInfo.outputPath('r07-timeline-desktop.png'), fullPage: true })
    await ownerPage.getByRole('tab', { name: '操作', exact: true }).click()
    await page.getByRole('link', { name: /^消息/ }).click()
    await expect(async () => {
      await page.getByRole('button', { name: '刷新消息', exact: true }).click()
      await expect(page.locator('.message-card')).toHaveCount(2)
    }).toPass({ timeout: 15000 })
    await expect(page.locator('.message-board')).toBeVisible()
    await expect(page.locator('.message-card.is-unread')).toHaveCount(2)
    await page.getByRole('button', { name: '仅看未读', exact: true }).click()
    await expect(page.getByRole('button', { name: '仅看未读', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('.message-card')).toHaveCount(2)
    await page.screenshot({ path: testInfo.outputPath('r07-messages-desktop.png'), fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('r07-messages-mobile.png'), fullPage: true })
    await page.setViewportSize({ width: 1280, height: 720 })
    await page.getByRole('button', { name: '全部消息', exact: true }).click()
    await expect(page.locator('.message-card')).toHaveCount(2)
    await page.getByRole('button', { name: '查看消息', exact: true }).first().click()
    await expect(page.locator('.issue-status').first()).toHaveText('已处理')
    await expect(page.getByLabel('目标状态', { exact: true })).toHaveCount(0)
    await page.locator('.comment-thread').getByRole('button', { name: '回复', exact: true }).click()
    await page.getByLabel(/^回复 @/).fill('替代资源已验证，可以使用。')
    await page.getByRole('button', { name: '发送回复', exact: true }).click()
    await expect(page.locator('.comment-thread')).toHaveCount(1)
    await expect(page.locator('.child-reply')).toHaveCount(1)
    await expect(page.locator('.reply-target')).toContainText('@路线创作者')
    await login(thirdPage, names[2]!, topicPath)
    await expect(thirdPage.getByLabel('目标状态', { exact: true })).toHaveCount(0)
    await thirdPage.locator('.child-reply').getByRole('button', { name: '回复', exact: true }).click()
    await thirdPage.getByLabel(/^回复 @/).fill('谢谢反馈！替代教程已核对，后续会继续检查其他资源。')
    await thirdPage.getByRole('button', { name: '发送回复', exact: true }).click()
    await expect(thirdPage.locator('.comment-thread')).toHaveCount(1)
    await expect(thirdPage.locator('.child-reply')).toHaveCount(2)
    await expect(thirdPage.locator('.child-reply .comment-byline').last()).toContainText('讨论参与者')
    await expect(thirdPage.locator('.comment-byline .reply-target').last()).toContainText('@学习探索者')
    await page.getByRole('link', { name: '问题与反馈', exact: true }).click()
    await page.getByRole('link', { name: '第三阶段视频链接失效，有替代资源吗？', exact: true }).click()
    await expect(page.locator('.child-reply')).toHaveCount(2)
    await page.screenshot({ path: testInfo.outputPath('r07-topic-desktop.png'), fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({ path: testInfo.outputPath('r07-topic-mobile.png'), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.locator('.child-reply .comment-byline a').first().click()
    await expect(page).toHaveURL(/\/users\/\d+$/)
    await expect(page.locator('.public-user-heading')).toContainText('学习探索者')
    // 新主页固定展示作品和动态，不在该页嵌入私人日历或入口。
    await expect(page.getByRole('link', { name: /查看我的打卡日历/ })).toHaveCount(0)
    await expect(page.locator('.calendar-panel')).toHaveCount(0)
    await page.screenshot({ path: testInfo.outputPath('r07-profile-mobile.png'), fullPage: true })
    const commentData = (await (await request.get('/api/v1' + topicPath, { headers: owner })).json()).data
    const rootComment = commentData.comments.items[0]
    const firstReply = rootComment.replies.items[0]
    expect((await request.delete('/api/v1' + topicPath + '/comments/' + rootComment.id, { headers: owner })).status()).toBe(200)
    expect((await request.delete('/api/v1' + topicPath + '/comments/' + firstReply.id, { headers: reader })).status()).toBe(200)
    await ownerPage.getByRole('link', { name: '全部话题', exact: true }).click()
    await ownerPage.getByRole('link', { name: '第三阶段视频链接失效，有替代资源吗？', exact: true }).click()
    await expect(ownerPage.locator('.comment-entry')).toHaveCount(1)
    await expect(ownerPage.locator('.child-reply')).toContainText('讨论参与者')
    await expect(ownerPage.locator('#comments')).not.toContainText('评论已删除')
    // 发布/回复/解决不切换学习版或推进节点。
    const after = (await (await request.get('/api/v1/enrollments/' + relation.id, { headers: reader })).json()).data
    expect(after.releaseId).toBe(originalRelease)
    expect(after.sessionId).toBe(relation.sessionId)
    expect(after.completedNodeCount).toBe(0)
    expect(after.hasNewVersion).toBe(true)
    await ownerPage.getByLabel('目标状态', { exact: true }).selectOption('closed')
    await expect(ownerPage.getByRole('button', { name: '保存状态', exact: true })).toBeDisabled()
    await ownerPage.getByLabel('处理原因（必填）', { exact: true }).fill('问题已确认，关闭重复讨论')
    await ownerPage.getByRole('button', { name: '保存状态', exact: true }).click()
    await expect(ownerPage.locator('.issue-status').first()).toHaveText('已关闭')
    await expect(ownerPage.getByRole('button', { name: '发送回复', exact: true })).toHaveCount(0)
    await ownerPage.getByRole('link', { name: '全部话题', exact: true }).click()
    await expect(ownerPage.locator('.topic-statistics')).toContainText(/1\s*已关闭/)
    await expect(ownerPage.locator('.topic-row .issue-status')).toHaveText('已关闭')
    const moreTopics = ['开始学习前需要掌握哪些基础？', '想补充一个变量与类型的练习', '这套学习顺序适合在校学生吗？', '目录中两处标题是否需要统一', '分享一下我完成练习的思路']
    for (const [index, topicTitle] of moreTopics.entries()) {
      const created = await request.post('/api/v1/roadmaps/' + rid + '/issues', { headers: owner, data: { title: topicTitle, body: '一起讨论这条路线的学习与改进。' } })
      expect(created.status()).toBe(201)
      if (index === 1 || index === 3) {
        const status = index === 3 ? 'closed' : 'resolved'
        expect((await request.patch('/api/v1/roadmaps/' + rid + '/issues/' + (await created.json()).data.id + '/state', { headers: owner, data: { status, expectedStatus: 'open', reason: '已整理并完成处理' } })).status()).toBe(200)
      }
    }
    await ownerPage.getByLabel('话题时间排序', { exact: true }).selectOption('createdAt:asc')
    await expect.poll(() => new URL(ownerPage.url()).searchParams.get('sort')).toBe('createdAt:asc')
    await expect(ownerPage.locator('.topic-row')).toHaveCount(6)
    await expect(ownerPage.locator('.topic-statistics strong').first()).toHaveText('6')
    await ownerPage.screenshot({ path: testInfo.outputPath('r07-list-desktop.png'), fullPage: true })
    await ownerPage.setViewportSize({ width: 390, height: 844 })
    await ownerPage.screenshot({ path: testInfo.outputPath('r07-list-mobile.png'), fullPage: true })
    expect(await ownerPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await ownerPage.getByLabel('处理状态筛选', { exact: true }).selectOption('open')
    await expect(ownerPage.locator('.topic-row')).toHaveCount(3)
    // 清理确认后的新投递必须保留；先等待此路线的事件完成，才能断言清空后为零。
    await expect.poll(() => Number(execFileSync('uv', ['run', 'python', '-c', `
import asyncio,sys
from sqlalchemy import text
from app.config.settings import Settings
from app.database.session import Database
async def main():
 db=Database(Settings().for_community_tests())
 try:
  async with db.sessions() as session:
   count=await session.scalar(text("SELECT COUNT(*) FROM notification_outbox WHERE status IN ('pending','processing') AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.roadmapId'))=:rid"),{'rid':sys.argv[1]})
   print(count)
 finally: await db.close()
asyncio.run(main())
`, rid], { cwd: backend, env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' }, stdio: 'pipe' }).toString().trim()), { timeout: 20000, intervals: [500, 1000] }).toBe(0)
    // 删除独立于原评论：此时原评论已删除，仍可移除历史通知。
    await page.getByRole('link', { name: /^消息/ }).click()
    await expect(page.locator('.message-card').first()).toBeVisible()
    const beforeDelete = await page.locator('.message-card').count()
    const deletedId = await page.locator('.message-card').first().getAttribute('data-notification-id')
    await page.getByRole('button', { name: '删除消息', exact: true }).first().click()
    await expect(page.getByRole('dialog', { name: '删除消息', exact: true })).toBeVisible()
    await page.getByRole('button', { name: '取消', exact: true }).click()
    await expect(page.locator('.message-card')).toHaveCount(beforeDelete)
    await page.getByRole('button', { name: '删除消息', exact: true }).first().click()
    await page.getByRole('button', { name: '确认删除', exact: true }).click()
    await expect(page.locator(`[data-notification-id="${deletedId}"]`)).toHaveCount(0)
    expect((await (await request.get('/api/v1/notifications', { headers: reader })).json()).data.items.some((item: { id: string }) => item.id === deletedId)).toBe(false)
    await page.getByRole('button', { name: '清理消息', exact: true }).click()
    await page.getByRole('button', { name: '清空历史消息', exact: true }).click()
    await page.screenshot({ path: testInfo.outputPath('r07-message-delete-mobile.png'), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('button', { name: '确认删除', exact: true }).click()
    await expect(page.locator('.message-card')).toHaveCount(0)
    await expect(page.locator('.messages-heading')).toContainText('0 条未读')
    await expect(page.locator('.message-link')).toHaveAttribute('aria-label', '消息')
    await expect(page.locator('.message-badge')).toHaveCount(0)
    await page.getByRole('button', { name: '刷新消息', exact: true }).click()
    await expect(page.locator('.message-state')).toContainText('暂时没有消息')
    await ownerPage.getByRole('link', { name: /^消息/ }).click()
    await expect(ownerPage.locator('.message-card').first()).toBeVisible()
    await ownerPage.getByRole('button', { name: '将当前列表及更早消息标为已读', exact: true }).click()
    await expect(ownerPage.locator('.messages-heading')).toContainText('0 条未读')
    await ownerPage.getByRole('button', { name: '清理消息', exact: true }).click()
    await ownerPage.getByRole('button', { name: '清理已读消息', exact: true }).click()
    await ownerPage.getByRole('button', { name: '确认删除', exact: true }).click()
    await expect(ownerPage.locator('.message-card')).toHaveCount(0)
    expect((await request.get('/api/v1' + topicPath, { headers: reader })).status()).toBe(200)
    expect(errors).toEqual([])
  } finally {
    await ownerContext.close()
    await thirdContext.close()
    const cleanup = [
      'import asyncio,sys', 'from app.config.settings import Settings', 'from app.database.session import Database',
      'from tests.route_cleanup import cleanup_routes', 'from tests.integration.test_accounts import cleanup_accounts',
      'async def main():', ' db=Database(Settings().for_community_tests())', ' try:',
      '  await cleanup_routes(db,set(sys.argv[1:]))', '  await cleanup_accounts(db,set(sys.argv[1:]))',
      ' finally: await db.close()', "if sys.platform=='win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())", 'asyncio.run(main())',
    ].join('\n')
    execFileSync('uv', ['run', 'python', '-c', cleanup, ...names], { cwd: backend, env: { ...process.env, PYTHONUTF8: '1' }, stdio: 'pipe' })
  }
})
