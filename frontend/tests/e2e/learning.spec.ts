import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

const backend = fileURLToPath(new URL('../../../backend/', import.meta.url))
test('R05与R06 学习恢复、打卡、跨版升级确认、过期预览及只读历史', async ({ page, request }, testInfo) => {
  test.setTimeout(180000)
  page.setDefaultTimeout(10000)
  const names = [0, 1].map(() => 'r02_' + randomUUID().replaceAll('-', '').slice(0, 24))
  const [owner, reader] = names as [string, string]
  const password = 'r05-browser-password'
  const title = '学习路线_' + randomUUID().slice(0, 8)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  try {
    for (const username of names) expect((await request.post('/api/v1/auth/register', { data: { username, password } })).status()).toBe(201)
    const logged = await request.post('/api/v1/auth/login', { data: { username: owner, password } })
    const author = { Authorization: 'Bearer ' + (await logged.json()).data.accessToken }
    const readerLogin = await request.post('/api/v1/auth/login', { data: { username: reader, password } })
    const readerHeaders = { Authorization: 'Bearer ' + (await readerLogin.json()).data.accessToken }
    const created = await request.post('/api/v1/roadmaps', { headers: author, data: { title } })
    expect(created.status()).toBe(201)
    const rid = (await created.json()).data.id as string
    const root = '/api/v1/roadmaps/' + rid
    const saved = await request.put(root + '/draft', { headers: author, data: {
      title, description: '适合初学者，从基础到实践。', licenseCode: 'UNLICENSED', expectedVersion: 1,
      stages: [{ id: 'tmp_s', title: '基础阶段', nodes: [0, 1].map(i => ({
        id: 'tmp_n' + i, title: '知识节点' + i, content: 'PRIVATE_R05_BODY_' + i,
        isOptional: i === 1, countsTowardProgress: i === 0,
        resources: [{ id: 'tmp_r' + i, title: '参考资源' + i, resourceType: 'article', resourceUrl: 'https://example.com/r05/' + i }],
      })) }], connections: [],
    } })
    expect(saved.status()).toBe(200)
    let document = (await saved.json()).data.document
    expect((await request.post(root + '/publish', { headers: author, data: { expectedVersion: document.expectedVersion, updateSummary: '首次发布' } })).status()).toBe(200)
    await page.setViewportSize({ width: 1536, height: 1024 })
    await page.goto('/roadmaps/' + rid)
    await expect(page.locator('.route-detail-page')).not.toContainText('PRIVATE_R05_BODY')
    await page.getByRole('button', { name: '开始学习', exact: true }).click()
    await expect(page).toHaveURL(/\/login$/)
    async function login() {
      await page.getByLabel('用户名', { exact: true }).fill(reader)
      await page.getByLabel('密码', { exact: true }).fill(password)
      await page.getByRole('button', { name: '登录', exact: true }).click()
    }
    await login()
    await expect(page).toHaveURL(/\/$/)
    await page.evaluate(target => {
      history.pushState(null, '', target)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, '/roadmaps/' + rid)
    await expect(page).toHaveURL(new RegExp('/roadmaps/' + rid + '$'))
    await page.getByRole('button', { name: '开始学习', exact: true }).click()
    await page.getByRole('button', { name: '确认开始学习', exact: true }).click()
    await expect(page).toHaveURL(/\/learning\/\d+$/)
    const learningUrl = page.url()
    const relationId = learningUrl.match(/learning\/(\d+)/)![1]!
    await expect(page.locator('.reader-content-body')).toContainText('PRIVATE_R05_BODY_0')
    await expect(page.locator('.progress-ring')).toHaveText('0%')
    await expect(page.getByRole('button', { name: '学习打卡', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '完成此节点', exact: true }).click()
    await expect(page.locator('.progress-ring')).toHaveText('100%')
    await expect(page.getByRole('button', { name: '学习打卡', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '撤销完成', exact: true }).click()
    await expect(page.locator('.progress-ring')).toHaveText('0%')
    const positionSaved = page.waitForResponse(response => response.url().endsWith('/position') && response.request().method() === 'PATCH')
    await page.getByRole('button', { name: '下一个节点', exact: true }).click()
    await expect(page.locator('.reader-content-body')).toContainText('PRIVATE_R05_BODY_1')
    expect((await positionSaved).status()).toBe(200)
    expect(relationId).toMatch(/^[0-9]+$/)
    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '我的学习', exact: true }).click()
    await expect(page.locator('.learning-card')).toHaveCount(1)
    const roadmapLink = page.locator('.learning-card').getByRole('link', { name: title, exact: true })
    await expect(roadmapLink).toHaveAttribute('href', '/roadmaps/' + rid)
    await roadmapLink.click()
    await expect(page).toHaveURL(new RegExp('/roadmaps/' + rid + '$'))
    await expect(page.locator('.route-detail-page')).toContainText(title)
    await page.getByRole('link', { name: '继续学习', exact: true }).click()
    await expect(page).toHaveURL(learningUrl)
    await expect(page.locator('.reader-content-body')).toContainText('PRIVATE_R05_BODY_1')
    await page.getByRole('button', { name: '学习打卡', exact: true }).click()
    await expect(page.getByRole('button', { name: '今日已打卡', exact: true })).toBeDisabled()
    await expect(page.locator('.progress-ring')).toHaveText('0%')
    await page.screenshot({ path: testInfo.outputPath('r05-learning-desktop.png'), fullPage: true })
    await page.getByRole('button', { name: '上一个节点', exact: true }).click()
    await page.getByRole('button', { name: '完成此节点', exact: true }).click()
    await expect(page.locator('.progress-ring')).toHaveText('100%')
    const sourcePositionSaved = page.waitForResponse(response => response.url().endsWith('/position') && response.request().method() === 'PATCH')
    await page.getByRole('button', { name: '下一个节点', exact: true }).click()
    expect((await sourcePositionSaved).status()).toBe(200)
    await page.getByRole('button', { name: '退出学习', exact: true }).click()
    await page.getByRole('button', { name: '确认退出学习', exact: true }).click()
    await expect(page.getByRole('button', { name: '恢复原版学习', exact: true })).toBeVisible()
    // 作者发布新版，恢复仍应读取原会话、原位置与原打卡资格。
    document.title = title + '新版'; document.stages[0].nodes[0].content = 'PRIVATE_NEW_VERSION'
    document.stages[0].nodes[0].changePolicy = 'reconfirm'
    document = (await (await request.put(root + '/draft', { headers: author, data: document })).json()).data.document
    expect((await request.post(root + '/publish', { headers: author, data: { expectedVersion: document.expectedVersion, updateSummary: '第二版' } })).status()).toBe(200)
    await page.getByRole('button', { name: '恢复原版学习', exact: true }).click()
    await expect(page).toHaveURL(learningUrl)
    await expect(page.locator('.reader-content-body')).toContainText('PRIVATE_R05_BODY_1')
    await expect(page.locator('.learning-content-page')).toContainText('已有新版 V2')
    await expect(page.getByRole('button', { name: '今日已打卡', exact: true })).toBeDisabled()
    await page.reload()
    await expect(page).toHaveURL(/\/login$/)
    await login()
    await expect(page).toHaveURL(/\/$/)
    await page.getByRole('link', { name: '我的学习', exact: true }).click()
    await page.getByRole('link', { name: '继续学习', exact: true }).click()
    await expect(page.locator('.reader-content-body')).toContainText('PRIVATE_R05_BODY_1')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({ path: testInfo.outputPath('r05-learning-mobile.png'), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('link', { name: '打卡记录', exact: true }).click()
    await expect(page.locator('.route-record-list li')).toHaveCount(1)
    await expect(page.locator('.learning-history-page')).not.toContainText('编辑收获')
    await page.getByRole('link', { name: '本人打卡日历', exact: true }).click()
    await expect(page.getByRole('heading', { name: '学习概览与打卡日历', exact: true })).toBeVisible()
    await expect(page.locator('.calendar-grid .checked')).toHaveCount(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('r05-calendar-mobile.png'), fullPage: true })
    // V1直接升V3仍识别V2语义变化；新主线任务改变分母。
    document.title = title + '第三版'
    document.stages[0].nodes[0].changePolicy = 'retain'
    document.stages[0].nodes.push({ id: 'tmp_added', title: '新增实践任务', content: 'PRIVATE_R06_ADDED',
      resources: [{ id: 'tmp_added_resource', title: '新增资源', resourceType: 'article', resourceUrl: 'https://example.com/r06-added' }] })
    document = (await (await request.put(root + '/draft', { headers: author, data: document })).json()).data.document
    expect((await request.post(root + '/publish', { headers: author, data: { expectedVersion: document.expectedVersion, updateSummary: '增加实践任务，更新学习要求' } })).status()).toBe(200)
    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '我的学习', exact: true }).click()
    await page.getByRole('link', { name: '继续学习', exact: true }).click()
    await expect(page.locator('.version-badge')).toHaveText('学习版 V1')
    await expect(page.locator('.progress-ring')).toHaveText('100%')
    await page.getByRole('button', { name: '查看版本差异', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('V1 → V3')
    await expect(page.getByRole('dialog')).toContainText('PRIVATE_R05_BODY_0')
    await expect(page.getByRole('dialog')).toContainText('PRIVATE_NEW_VERSION')
    await expect(page.getByRole('button', { name: '确认升级', exact: true })).toBeDisabled()
    await page.getByRole('button', { name: '暂不升级', exact: true }).click()
    await expect(page.locator('.version-badge')).toHaveText('学习版 V1')
    await page.getByRole('button', { name: '查看版本差异', exact: true }).click()
    await page.getByLabel('任务确认：知识节点0', { exact: true }).selectOption('keep')
    await expect(page.getByRole('dialog')).toContainText('升级后：1 / 2 · 50%')
    const oldContent = (await (await request.get('/api/v1/enrollments/' + relationId + '/content', { headers: readerHeaders })).json()).data
    const oldSessionId = oldContent.enrollment.sessionId as string
    const optionalNodeId = oldContent.stages[0].nodes[1].id as string
    expect((await request.put('/api/v1/enrollments/' + relationId + '/nodes/' + optionalNodeId + '/status', {
      headers: readerHeaders, data: { sessionId: oldSessionId, completed: true },
    })).status()).toBe(200)
    await page.getByRole('button', { name: '确认升级', exact: true }).click()
    await expect(page.getByRole('dialog').getByRole('alert')).toContainText('学习位置或进度已变化')
    await expect(page.getByRole('button', { name: '确认升级', exact: true })).toBeDisabled()
    await page.getByRole('button', { name: '重新查看差异', exact: true }).click()
    await expect(page.getByLabel('任务确认：知识节点0', { exact: true })).toHaveValue('')
    await page.getByLabel('任务确认：知识节点0', { exact: true }).selectOption('keep')
    await page.screenshot({ path: testInfo.outputPath('r06-upgrade-mobile.png'), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.setViewportSize({ width: 1536, height: 1024 })
    await page.screenshot({ path: testInfo.outputPath('r06-upgrade-desktop.png'), fullPage: true })
    await page.getByRole('button', { name: '确认升级', exact: true }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.locator('.version-badge')).toHaveText('学习版 V3')
    await expect(page.locator('.progress-ring')).toHaveText('50%')
    await expect(page.getByRole('button', { name: '今日已打卡', exact: true })).toBeDisabled()
    expect((await request.post('/api/v1/enrollments/' + relationId + '/records', { headers: readerHeaders, data: { sessionId: oldSessionId } })).status()).toBe(409)
    await page.getByRole('link', { name: '版本历史', exact: true }).click()
    await expect(page.locator('.learning-version-list li')).toHaveCount(2)
    await page.getByRole('link', { name: '回顾此版本', exact: true }).click()
    await expect(page.locator('.learning-content-page')).toContainText('这是历史学习版本，仅供回顾')
    await page.getByRole('button', { name: '知识节点0', exact: true }).click()
    await expect(page.locator('.reader-content-body')).toContainText('PRIVATE_R05_BODY_0')
    await expect(page.locator('.progress-ring')).toHaveText('100%')
    await expect(page.getByRole('button', { name: '撤销完成', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: '退出学习', exact: true })).toHaveCount(0)
    await page.screenshot({ path: testInfo.outputPath('r06-history-desktop.png'), fullPage: true })
    await page.getByRole('link', { name: '返回当前学习', exact: true }).click()
    await expect(page.locator('.version-badge')).toHaveText('学习版 V3')
    expect(errors).toEqual([])
  } finally {
    const cleanup = [
      'import asyncio,sys',
      'from app.config.settings import Settings',
      'from app.database.session import Database',
      'from tests.route_cleanup import cleanup_routes',
      'from tests.integration.test_accounts import cleanup_accounts',
      'async def main():',
      ' db=Database(Settings().for_community_tests())',
      ' try:',
      '  await cleanup_routes(db,set(sys.argv[1:]))',
      '  await cleanup_accounts(db,set(sys.argv[1:]))',
      ' finally: await db.close()',
      "if sys.platform=='win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())",
      'asyncio.run(main())',
    ].join('\n')
    execFileSync('uv', ['run', 'python', '-c', cleanup, ...names], { cwd: backend, env: { ...process.env, PYTHONUTF8: '1' }, stdio: 'pipe' })
  }
})
