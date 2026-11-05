import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

const backend = fileURLToPath(new URL('../../../backend/', import.meta.url))

test('R04公开快照、搜索分页、固定登录跳转、收藏及归档恢复', async ({ page, request }, testInfo) => {
  test.setTimeout(180000)
  const names = [0, 1].map(() => 'r02_' + randomUUID().replaceAll('-', '').slice(0, 24))
  const owner = names[0]!, reader = names[1]!
  const password = 'r04-browser-password'
  const keyword = '探索路线_' + randomUUID().slice(0, 8)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const ids: string[] = []
  const versions: number[] = []
  try {
    for (const username of names) {
      const result = await request.post('/api/v1/auth/register', { data: { username, password, nickname: username === owner ? '路线分享者' : '路线探索者' } })
      expect(result.status()).toBe(201)
    }
    const login = await request.post('/api/v1/auth/login', { data: { username: owner, password } })
    expect(login.status()).toBe(200)
    const headers = { Authorization: 'Bearer ' + (await login.json()).data.accessToken }
    for (let i = 0; i < 14; i++) {
      const created = await request.post('/api/v1/roadmaps', { headers, data: { title: keyword } })
      expect(created.status()).toBe(201)
      const id = (await created.json()).data.id as string
      const saved = await request.put('/api/v1/roadmaps/' + id + '/draft', { headers, data: {
        expectedVersion: 1, title: keyword + ' · ' + (i + 1), description: '从基础概念到动手实践，沿着清晰的阶段探索知识。',
        licenseCode: 'UNLICENSED', difficulty: i === 0 ? 'advanced' : 'beginner', connections: [],
        stages: [{ id: 'tmp_s', title: '基础与实践', nodes: [{ id: 'tmp_n', title: '开始探索', content: 'PRIVATE_R04_BODY',
          resources: [{ id: 'tmp_r', title: '参考资源', resourceType: 'article', resourceUrl: 'https://example.com/private-r04' }] }] }],
      } })
      expect(saved.status()).toBe(200)
      const version = (await saved.json()).data.document.expectedVersion as number
      if (i < 13) {
        expect((await request.post('/api/v1/roadmaps/' + id + '/publish', { headers, data: { expectedVersion: version, updateSummary: '首次分享' } })).status()).toBe(200)
        ids.push(id); versions.push(version)
      }
    }
    await page.setViewportSize({ width: 1536, height: 1024 })
    await page.goto('/?q=' + encodeURIComponent(keyword))
    await expect(page.getByRole('heading', { name: '发现一条适合你的学习路线', exact: true })).toBeVisible()
    await expect(page.locator('.discovery-card')).toHaveCount(12)
    await expect(page.locator('.discovery-results-heading')).toContainText('13 条路线')
    await expect(page.locator('.discovery-page')).not.toContainText('社区共建')
    await expect(page.locator('.discovery-page')).not.toContainText('继续学习')
    await page.screenshot({ path: testInfo.outputPath('r04-community-desktop.png'), fullPage: true })
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await expect(page).toHaveURL(/page=2/)
    await expect(page.locator('.discovery-card')).toHaveCount(1)
    await page.getByRole('button', { name: '高级', exact: true }).click()
    await expect(page).not.toHaveURL(/page=2/)
    await expect(page.locator('.discovery-card')).toHaveCount(1)
    await page.getByLabel('路线排序', { exact: true }).selectOption('favoriteCount:desc')
    await expect(page).toHaveURL(/sortBy=favoriteCount/)
    await page.locator('.discovery-card').getByRole('button', { name: /^收藏：/ }).click()
    await expect(page).toHaveURL(/\/login$/)
    await page.getByLabel('用户名', { exact: true }).fill(reader)
    await page.getByLabel('密码', { exact: true }).fill(password)
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    await page.evaluate(target => {
      history.pushState(null, '', target)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, '/roadmaps/' + ids[0])
    await expect(page).toHaveURL(new RegExp('/roadmaps/' + ids[0] + '$'))
    await expect(page.getByRole('button', { name: '收藏', exact: true })).toBeVisible()
    await expect(page.locator('.route-detail-page')).not.toContainText('PRIVATE_R04_BODY')
    await expect(page.getByRole('region', { name: '学习路线结构' })).toContainText('开始探索')
    await expect(page.getByLabel('路线目录', { exact: true })).toHaveCount(0)
    await expect(page.locator('.route-detail-page .route-badge')).toHaveCount(0)
    await page.screenshot({ path: testInfo.outputPath('r04-detail-desktop.png'), fullPage: true })
    await page.getByRole('button', { name: '收藏', exact: true }).click()
    await expect(page.getByRole('button', { name: '取消收藏', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '我的收藏', exact: true }).click()
    await expect(page.locator('.discovery-card')).toHaveCount(1)
    await expect(page.locator('.fresh-social-stats')).toContainText('1 人收藏')
    await expect(page.locator('.fresh-social-stats')).toContainText('0 人学习')
    await expect(page.locator('.discovery-card-footer button')).toHaveText('取消收藏')
    const authorPath = await page.locator('.fresh-author').getAttribute('href')
    expect(authorPath).toMatch(/^\/users\/\d+$/)
    await page.locator('.fresh-author-name').click()
    await expect.poll(() => new URL(page.url()).pathname).toBe(authorPath)
    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '我的收藏', exact: true }).click()
    await expect(page.locator('.fresh-social-stats')).toContainText('1 人收藏')
    await page.screenshot({ path: testInfo.outputPath('r04-favorites-desktop.png'), fullPage: true })
    const id = ids[0]!
    expect((await request.post('/api/v1/roadmaps/' + id + '/archive', { headers, data: { expectedVersion: versions[0] } })).status()).toBe(200)
    await page.reload()
    await expect(page).toHaveURL(/\/login$/)
    await page.getByLabel('用户名', { exact: true }).fill(reader)
    await page.getByLabel('密码', { exact: true }).fill(password)
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
    await page.getByRole('link', { name: '我的收藏', exact: true }).click()
    await expect(page.locator('.restricted-copy')).toContainText('路线暂不可访问')
    await expect(page.locator('.discovery-card').getByRole('link')).toHaveCount(0)
    await page.screenshot({ path: testInfo.outputPath('r04-restricted-favorite.png'), fullPage: true })
    expect((await request.post('/api/v1/roadmaps/' + id + '/restore', { headers, data: { expectedVersion: versions[0] } })).status()).toBe(200)
    const draft = (await (await request.get('/api/v1/roadmaps/' + id + '/draft', { headers })).json()).data.document
    draft.title = keyword + ' · 全新版本'
    const saved = (await (await request.put('/api/v1/roadmaps/' + id + '/draft', { headers, data: draft })).json()).data
    expect((await (await request.get('/api/v1/roadmaps/' + id)).json()).data.title).not.toContain('全新版本')
    expect((await request.post('/api/v1/roadmaps/' + id + '/publish', { headers, data: { expectedVersion: saved.document.expectedVersion, updateSummary: '完善资源' } })).status()).toBe(200)
    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '社区发现', exact: true }).click()
    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '我的收藏', exact: true }).click()
    await expect(page.locator('.discovery-card')).toContainText('全新版本')
    await expect(page.locator('.discovery-card')).toContainText('V2')
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.locator('.discovery-card').getByRole('button', { name: /^取消收藏：/ })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('r04-favorites-mobile.png'), fullPage: true })
    await page.locator('.discovery-card').getByRole('button', { name: /^取消收藏：/ }).click()
    await expect(page.getByRole('heading', { name: '还没有收藏路线', exact: true })).toBeVisible()
    await page.getByRole('link', { name: '去社区发现', exact: true }).click()
    await page.getByLabel('想学什么？', { exact: true }).fill(keyword)
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await expect(page.locator('.discovery-card')).toHaveCount(12)
    await expect(page.locator('.fresh-social-stats').first()).toContainText('人收藏')
    await expect(page.locator('.fresh-social-stats').first()).toContainText('人学习')
    await expect(page.locator('.discovery-card-footer button').first()).toHaveText('收藏')
    await expect(page.locator('.fresh-author').first()).toHaveAttribute('href', authorPath!)
    await page.screenshot({ path: testInfo.outputPath('r04-community-mobile.png'), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    // 页面不溢出仍可能把卡片内容裁掉，逐项验证作者与收藏按钮位于卡片内部。
    const cardBounds = await page.locator('.discovery-card').first().boundingBox()
    for (const selector of ['.fresh-card-meta', '.discovery-card-footer', '.discovery-card-footer button']) {
      const bounds = await page.locator('.discovery-card').first().locator(selector).boundingBox()
      expect(bounds).not.toBeNull()
      expect(bounds!.x).toBeGreaterThanOrEqual(cardBounds!.x)
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(cardBounds!.x + cardBounds!.width)
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(cardBounds!.y + cardBounds!.height)
    }
    await page.route('**/api/v1/roadmaps?**', route => route.abort())
    await page.getByRole('button', { name: '高级', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('无法连接服务')
    await page.unroute('**/api/v1/roadmaps?**')
    await page.getByRole('button', { name: '重新加载', exact: true }).click()
    await expect(page.locator('.discovery-card')).toHaveCount(1)
    await page.locator('.fresh-author .user-avatar').click()
    await expect.poll(() => new URL(page.url()).pathname).toBe(authorPath)
    await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '社区发现', exact: true }).click()
    await page.getByLabel('想学什么？', { exact: true }).fill(keyword)
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await page.getByRole('button', { name: '高级', exact: true }).click()
    await expect(page.locator('.discovery-card')).toHaveCount(1)
    await page.locator('.discovery-card-link').click()
    await expect(page.getByRole('region', { name: '学习路线结构' })).toContainText('开始探索')
    await page.screenshot({ path: testInfo.outputPath('r04-detail-mobile.png'), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
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
    execFileSync('uv', ['run', 'python', '-c', cleanup, ...names], {
      cwd: backend, env: { ...process.env, PYTHONUTF8: '1' }, stdio: 'pipe',
    })
  }
})
