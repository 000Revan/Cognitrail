import { http } from './http'
import { getAccessToken, handleUnauthorized } from './session'
import type { ApiResponse } from '../types/common'
import type { ChatEvent, ChatRequest, ConversationDetail, ConversationSummary } from '../types/agent'

export async function getConversations(): Promise<ConversationSummary[]> {
  return (await http.get<ApiResponse<ConversationSummary[]>>('/api/v1/agent/conversations')).data.data
}

export async function getConversationMessages(id: string): Promise<ConversationDetail> {
  return (await http.get<ApiResponse<ConversationDetail>>(
    `/api/v1/agent/conversations/${encodeURIComponent(id)}/messages`,
  )).data.data
}

/** POST SSE：前端只提交问题和会话 ID，不提供模型历史。 */
export async function streamChat(payload: ChatRequest, onEvent: (event: ChatEvent) => void): Promise<void> {
  const token = getAccessToken()
  const authorization = token ? `Bearer ${token}` : ''
  const baseURL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
  const response = await fetch(`${baseURL}/api/v1/agent/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(authorization ? { Authorization: authorization } : {}),
    },
    body: JSON.stringify(payload),
  })
  if (response.status === 401) handleUnauthorized(authorization)
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(error?.msg || `请求失败（${response.status}）`)
  }
  if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) {
    throw new Error('服务未返回 SSE 数据流')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let ended = false

  function dispatch(block: string) {
    let eventName = 'message'
    const dataLines: string[] = []
    for (const line of block.split(/\r?\n/)) {
      if (!line || line.startsWith(':')) continue
      const colon = line.indexOf(':')
      const field = colon === -1 ? line : line.slice(0, colon)
      let value = colon === -1 ? '' : line.slice(colon + 1)
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'event') eventName = value
      if (field === 'data') dataLines.push(value)
    }
    if (!dataLines.length) return
    const data = JSON.parse(dataLines.join('\n'))
    if (eventName === 'conversation') onEvent({ event: 'conversation', data })
    else if (eventName === 'delta') onEvent({ event: 'delta', data })
    else if (eventName === 'reset') onEvent({ event: 'reset', data })
    else if (eventName === 'intent') onEvent({ event: 'intent', data })
    else if (eventName === 'done') {
      ended = true
      onEvent({ event: 'done', data })
    } else if (eventName === 'error') {
      ended = true
      onEvent({ event: 'error', data })
    }
  }

  try {
    while (!ended) {
      const { value, done } = await reader.read()
      if (done) break
      // 网络块不等于事件；保留跨块的 UTF-8 和半个事件。
      buffer += decoder.decode(value, { stream: true })
      let separator = /\r?\n\r?\n/.exec(buffer)
      while (separator && !ended) {
        const block = buffer.slice(0, separator.index)
        buffer = buffer.slice(separator.index + separator[0].length)
        dispatch(block)
        separator = /\r?\n\r?\n/.exec(buffer)
      }
    }
    if (!ended) throw new Error('连接已中断，本轮未确认完成，请重新打开会话查看')
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
