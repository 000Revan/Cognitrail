/** 凭证仅存在模块内存中，不写入浏览器持久存储。 */
let accessToken: string | null = null
let expiredHandler: (() => void) | null = null

export function getAccessToken(): string | null { return accessToken }
export function setAccessToken(token: string | null) { accessToken = token }
export function onSessionExpired(handler: () => void) { expiredHandler = handler }
export function handleUnauthorized(sentAuthorization: unknown) {
  // 迟到的旧请求不能清除刚刚登录的新会话。
  if (accessToken && sentAuthorization === `Bearer ${accessToken}`) expiredHandler?.()
}
