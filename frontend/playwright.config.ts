import { defineConfig } from '@playwright/test'
import { fileURLToPath } from 'node:url'

// 使用独立端口，避免复用用户正在验收的旧后端进程。
const backendPort = process.env.E2E_BACKEND_PORT || '18000'
const frontendPort = process.env.E2E_FRONTEND_PORT || '15173'
const backendUrl = `http://127.0.0.1:${backendPort}`
const frontendUrl = `http://127.0.0.1:${frontendPort}`
// 多个账号流程共享测试服务；仅测试进程使用独立配额，生产默认仍10次/60秒。
const loginLimit = process.env.E2E_LOGIN_RATE_LIMIT || '30'
const testDatabase = process.env.TEST_DB_NAME
if (!testDatabase || !/^cognitrail_community_test(?:_[a-zA-Z0-9]+)*$/.test(testDatabase)) {
  throw new Error('请显式设置 TEST_DB_NAME=cognitrail_community_test，浏览器账号测试禁止使用开发库或旧库')
}

export default defineConfig({
  testDir: './tests/e2e',
  // 旧业务用例含真实账号与清理操作，按R02—R09适配后逐项恢复。
  testMatch: ['health.spec.ts', 'accounts.spec.ts', 'roadmaps.spec.ts', 'discovery.spec.ts', 'learning.spec.ts', 'issues.spec.ts'],
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: frontendUrl,
    channel: process.env.PLAYWRIGHT_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined),
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `uv run --project ../backend python -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port ${backendPort} --no-proxy-headers`,
      url: `${backendUrl}/health/live`,
      reuseExistingServer: false,
      env: { PYTHONUTF8: '1', LOGIN_RATE_LIMIT: loginLimit, DB_NAME: testDatabase, LOG_LEVEL: 'WARNING', AVATAR_STORAGE_DIR: fileURLToPath(new URL('../backend/.cache/e2e-avatars', import.meta.url)) },
    },
    {
      command: `pnpm exec vite --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      url: frontendUrl,
      reuseExistingServer: false,
      env: { VITE_API_PROXY_TARGET: backendUrl },
    },
  ],
})
