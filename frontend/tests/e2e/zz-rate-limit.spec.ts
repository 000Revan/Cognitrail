import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

test('真实服务器的登录限流不会被客户端转发头绕过', async ({ request }) => {
  const data = { username: 'missing_' + randomUUID().replaceAll('-', '').slice(0, 20), password: 'Never-a-real-password-123' }
  let limited = false
  const limit = Number(process.env.E2E_LOGIN_RATE_LIMIT || '30')
  for (let attempt = 0; attempt <= limit; attempt++) {
    const response = await request.post('/api/v1/auth/login', { data })
    if (response.status() === 429) {
      expect(Number(response.headers()['retry-after'])).toBeGreaterThan(0)
      limited = true
      break
    }
    expect(response.status()).toBe(401)
  }
  expect(limited).toBe(true)
  const spoofed = await request.post('/api/v1/auth/login', {
    data, headers: { 'X-Forwarded-For': '203.0.113.100' },
  })
  expect(spoofed.status()).toBe(429)
  expect((await spoofed.json()).data.errorCode).toBe('LOGIN_RATE_LIMITED')
})
