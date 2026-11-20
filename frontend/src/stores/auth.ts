import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as authApi from '../api/auth'
import { getAccessToken, onSessionExpired, readStoredSession, setAccessToken } from '../api/session'
import { ApiError } from '../api/http'
import * as userApi from '../api/user'
import type { LoginRequest } from '../types/auth'
import type { ProfileUpdate, UserPublic } from '../types/user'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserPublic | null>(null)
  const expiresAt = ref<number | null>(null)
  const sessionVersion = ref(0)
  const endReason = ref<'expired' | 'logout' | 'passwordChanged'>('expired')
  const restoring = ref(false)
  const restoreError = ref('')
  let initialized = false
  let restorePromise: Promise<void> | null = null
  let expiryTimer: ReturnType<typeof setTimeout> | undefined
  const authenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.role === 'admin')

  function clear(reason: 'expired' | 'logout' | 'passwordChanged' = 'expired') {
    sessionVersion.value++
    clearTimeout(expiryTimer)
    setAccessToken(null)
    user.value = null
    expiresAt.value = null
    endReason.value = reason
    restoreError.value = ''
    initialized = true
  }
  onSessionExpired(clear)

  function scheduleExpiry(deadline: number) {
    clearTimeout(expiryTimer)
    expiresAt.value = deadline
    expiryTimer = setTimeout(clear, Math.max(0, deadline - Date.now()))
  }

  /** 首次导航恢复身份；并发调用共用请求，失败不以本地资料冒充已登录。 */
  function restoreSession(): Promise<void> {
    if (initialized) return Promise.resolve()
    if (restorePromise) return restorePromise
    const saved = readStoredSession()
    if (!saved || saved.expiresAt <= Date.now()) {
      clear()
      return Promise.resolve()
    }
    const ticket = sessionVersion.value
    setAccessToken(saved.accessToken, saved.expiresAt)
    restoring.value = true
    restoreError.value = ''
    restorePromise = (async () => {
      try {
        const profile = await userApi.getMe()
        if (ticket !== sessionVersion.value || getAccessToken() !== saved.accessToken) return
        if (saved.expiresAt <= Date.now()) {
          clear()
          return
        }
        user.value = profile
        scheduleExpiry(saved.expiresAt)
        initialized = true
      } catch (error) {
        // 旧恢复请求不能影响随后完成的登录或退出。
        if (ticket !== sessionVersion.value || getAccessToken() !== saved.accessToken) return
        if (error instanceof ApiError && error.status === 401) {
          clear()
          return
        }
        restoreError.value = '暂时无法恢复登录，请检查网络后重试'
        throw error
      } finally {
        restoring.value = false
      }
    })().finally(() => { restorePromise = null })
    return restorePromise
  }

  async function login(data: LoginRequest) {
    const ticket = ++sessionVersion.value
    const response = await authApi.login(data)
    if (ticket !== sessionVersion.value) return false
    clear()
    const deadline = Date.now() + response.expiresIn * 1000
    setAccessToken(response.accessToken, deadline)
    user.value = response.user
    scheduleExpiry(deadline)
    return true
  }

  async function logout() {
    const sentToken = getAccessToken()
    const ticket = sessionVersion.value
    await authApi.logout()
    if (ticket === sessionVersion.value && sentToken === getAccessToken()) clear('logout')
  }

  function requireSameSession(sentToken: string | null, ticket: number) {
    if (!sentToken || sentToken !== getAccessToken() || ticket !== sessionVersion.value) {
      throw new Error('账号已切换，请重新操作')
    }
  }

  async function refreshProfile() {
    const sentToken = getAccessToken()
    const ticket = sessionVersion.value
    const profile = await userApi.getMe()
    requireSameSession(sentToken, ticket)
    user.value = profile
    return profile
  }

  async function saveProfile(data: ProfileUpdate) {
    const sentToken = getAccessToken()
    const ticket = sessionVersion.value
    const profile = await userApi.updateMe(data)
    requireSameSession(sentToken, ticket)
    user.value = profile
    return profile
  }

  async function uploadAvatar(file: File) {
    const sentToken = getAccessToken()
    const ticket = sessionVersion.value
    const profile = await userApi.uploadAvatar(file)
    requireSameSession(sentToken, ticket)
    if (user.value) user.value = { ...user.value, avatarUrl: profile.avatarUrl }
    return profile
  }

  return { user, expiresAt, sessionVersion, endReason, authenticated, isAdmin, restoring, restoreError,
    login, logout, clear, restoreSession, refreshProfile, saveProfile, uploadAvatar }
})
