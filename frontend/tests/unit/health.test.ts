import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getLiveHealth, getReadyHealth } from '../../src/api/health'
import { ApiError } from '../../src/api/http'
import { useHealthStore } from '../../src/stores/health'

vi.mock('../../src/api/health', () => ({ getLiveHealth: vi.fn(), getReadyHealth: vi.fn() }))

beforeEach(() => setActivePinia(createPinia()))

describe('真实检查结果的状态管理', () => {
  it('数据库失败不会覆盖后端进程成功，保留请求编号', async () => {
    vi.mocked(getLiveHealth).mockResolvedValue({ service: 'Cognitrail', status: 'alive', checkedAt: '2026-10-29T00:00:00Z' })
    vi.mocked(getReadyHealth).mockRejectedValue(new ApiError('数据库未就绪', 503, 'DATABASE_NOT_READY', 'request-1'))
    const health = useHealthStore()
    await health.refresh()
    expect(health.live.status).toBe('success')
    expect(health.ready.status).toBe('error')
    expect(health.ready.requestId).toBe('request-1')
    expect(health.databaseInfo).toBeNull()
    expect(health.loading).toBe(false)
  })

  it('重试成功清除旧错误和请求编号，不保留过期的数据库状态', async () => {
    vi.mocked(getLiveHealth).mockResolvedValue({ service: 'Cognitrail', status: 'alive', checkedAt: '2026-10-29T00:00:00Z' })
    vi.mocked(getReadyHealth).mockRejectedValueOnce(new ApiError('连接失败', 503, 'DATABASE_NOT_READY', 'old-request'))
    const health = useHealthStore()
    await health.refresh()
    vi.mocked(getReadyHealth).mockResolvedValueOnce({
      status: 'ready', database: 'connected', databaseVersion: '8.0.14',
      migrationRevision: '0004_roadmap_canvas', timezone: 'Asia/Shanghai', checkedAt: '2026-10-31T00:00:00Z',
    })
    await health.refresh()
    expect(health.ready.status).toBe('success')
    expect(health.ready.requestId).toBeUndefined()
    expect(health.databaseInfo?.databaseVersion).toBe('8.0.14')
    expect(health.databaseInfo?.migrationRevision).toBe('0004_roadmap_canvas')
  })
})
