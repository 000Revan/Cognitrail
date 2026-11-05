import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getLiveHealth, getReadyHealth } from '../api/health'
import { ApiError } from '../api/http'
import type { CheckResult, ReadyHealth } from '../types/health'

function failedResult(error: unknown): CheckResult {
  return {
    status: 'error',
    message: error instanceof Error ? error.message : '检查未完成，请稍后重试',
    requestId: error instanceof ApiError ? error.requestId : undefined,
  }
}

export const useHealthStore = defineStore('health', () => {
  const loading = ref(false)
  const live = ref<CheckResult>({ status: 'idle', message: '等待检查' })
  const ready = ref<CheckResult>({ status: 'idle', message: '等待检查' })
  const databaseInfo = ref<ReadyHealth | null>(null)
  const checkedAt = ref<string | null>(null)

  async function refresh() {
    if (loading.value) return
    loading.value = true
    databaseInfo.value = null
    live.value = { status: 'checking', message: '正在连接后端…' }
    ready.value = { status: 'checking', message: '正在检查数据库与迁移…' }
    // 两项独立更新；数据库超时不应掩盖已成功的进程检查。
    await Promise.all([
      getLiveHealth().then(() => {
        live.value = { status: 'success', message: '后端进程运行正常，前端请求已成功到达。' }
      }).catch(error => { live.value = failedResult(error) }),
      getReadyHealth().then(data => {
        databaseInfo.value = data
        ready.value = { status: 'success', message: '数据库已连接，迁移版本与项目一致。' }
      }).catch(error => { ready.value = failedResult(error) }),
    ])
    checkedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    loading.value = false
  }

  return { loading, live, ready, databaseInfo, checkedAt, refresh }
})
