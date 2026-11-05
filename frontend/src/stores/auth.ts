import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as authApi from '../api/auth'
import { getAccessToken, onSessionExpired, setAccessToken } from '../api/session'
import * as userApi from '../api/user'
import type { LoginRequest } from '../types/auth'
import type { ProfileUpdate, UserPublic } from '../types/user'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserPublic | null>(null)
  const expiresAt = ref<number | null>(null)
  const sessionVersion = ref(0)
  const endReason = ref<'expired' | 'logout' | 'passwordChanged'>('expired')
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
  }
  onSessionExpired(clear)

  async function login(data: LoginRequest) {
    const ticket = ++sessionVersion.value
    const response = await authApi.login(data)
    if (ticket !== sessionVersion.value) return false
    clear()
    setAccessToken(response.accessToken)
    user.value = response.user
    expiresAt.value = Date.now() + response.expiresIn * 1000
    expiryTimer = setTimeout(clear, response.expiresIn * 1000)
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

  return { user, expiresAt, sessionVersion, endReason, authenticated, isAdmin,
    login, logout, clear, refreshProfile, saveProfile, uploadAvatar }
})
