/** 内存供请求读取；sessionStorage 只保存当前标签页的凭证和原到期时间。 */
const STORAGE_KEY = 'cognitrail.auth'
let accessToken: string | null = null
let expiredHandler: (() => void) | null = null

export function getAccessToken(): string | null { return accessToken }
export function setAccessToken(token: string | null, expiresAt?: number) {
  accessToken = token
  if (token && expiresAt !== undefined) {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ accessToken: token, expiresAt }))
  } else {
    sessionStorage.removeItem(STORAGE_KEY)
  }
}

export function readStoredSession(): { accessToken: string; expiresAt: number } | null {
  const saved = sessionStorage.getItem(STORAGE_KEY)
  if (!saved) return null
  try {
    const value = JSON.parse(saved)
    if (value && typeof value.accessToken === 'string' && value.accessToken &&
        typeof value.expiresAt === 'number' && Number.isFinite(value.expiresAt)) return value
  } catch { /* 无法读取的旧记录按未登录处理。 */ }
  sessionStorage.removeItem(STORAGE_KEY)
  return null
}
export function onSessionExpired(handler: () => void) { expiredHandler = handler }
export function handleUnauthorized(sentAuthorization: unknown) {
  // 迟到的旧请求不能清除刚刚登录的新会话。
  if (accessToken && sentAuthorization === `Bearer ${accessToken}`) expiredHandler?.()
}
