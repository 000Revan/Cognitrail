import { expect, test } from '@playwright/test'

test('社区分阶段入口保持登录边界，未交付API仍受控', async ({ page, request }) => {
  const businessRequests: string[] = []
  page.on('request', req => {
    if (new URL(req.url()).pathname.startsWith('/api/v1/')) businessRequests.push(req.url())
  })
  await page.goto('/admin/roadmaps')
  await expect(page).toHaveURL(/\/login$/)
  for (const path of ['/profile']) {
    await page.goto(path)
    await expect(page).toHaveURL(/\/login$/)
  }
  await page.goto('/preparing')
  await expect(page.getByRole('heading', { name: '公开社区正在升级' })).toBeVisible()
  expect(businessRequests).toEqual([])
  for (const path of ['/api/v1/admin/roadmaps', '/api/v1/admin/roadmaps/1']) {
    const response = await request.get(path)
    expect(response.status()).toBe(401)
  }
  const pending = await request.post('/api/v1/roadmaps/1/withdraw', { data: { expectedVersion: 1 } })
  expect(pending.status()).toBe(503)
  expect((await pending.json()).data.errorCode).toBe('COMMUNITY_FEATURE_NOT_READY')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('link', { name: '查看运行状态' }).click()
  await expect(page).toHaveURL(/\/environment$/)
})

test('前端通过真实代理访问后端，并如实展示数据库状态', async ({ page, request }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const readyResponse = await request.get('/health/ready')
  if (process.env.EXPECT_DATABASE_READY === '1') expect(readyResponse.status()).toBe(200)
  const readyPayload = await readyResponse.json()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/environment')
  await expect(page.getByTestId('live-card')).toContainText('已就绪')
  if (readyResponse.ok()) {
    await expect(page.getByTestId('ready-card')).toContainText('已就绪')
    await expect(page.getByLabel('已验证环境信息')).toContainText(readyPayload.data.databaseVersion)
  } else {
    expect(readyResponse.status()).toBe(503)
    await expect(page.getByTestId('ready-card')).toContainText('未就绪')
    await expect(page.getByTestId('ready-card')).toContainText(readyPayload.msg)
  }
  await page.getByRole('button', { name: /重新检查/ }).click()
  await expect(page.getByRole('button', { name: /重新检查/ })).toBeEnabled()
  await page.screenshot({ path: testInfo.outputPath('overview-desktop.png'), fullPage: true })
  await page.context().setOffline(true)
  await page.getByRole('button', { name: /重新检查/ }).click()
  await expect(page.getByTestId('live-card')).toContainText('无法连接服务')
  await page.context().setOffline(false)
  await page.getByRole('button', { name: /重新检查/ }).click()
  await expect(page.getByTestId('live-card')).toContainText('已就绪')
  await expect(page.getByRole('button', { name: /重新检查/ })).toBeEnabled()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('overview-mobile.png'), fullPage: true })
  expect(errors).toEqual([])
})
