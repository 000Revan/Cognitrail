export type BusinessIntent = 'route_search' | 'route_create'
export type AgentIntent = BusinessIntent | 'chat' | 'clarify'

export interface ChatRequest {
  message: string
  conversationId: string | null
  intentHint?: BusinessIntent | null
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: string
}

export interface ConversationSummary {
  id: string
  title: string
  createdAt: string
  updatedAt: string
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[]
}

export type ChatEvent =
  | { event: 'conversation'; data: { conversationId: string } }
  | { event: 'delta'; data: { text: string } }
  | { event: 'reset'; data: Record<string, never> }
  | { event: 'intent'; data: { resolvedIntent: AgentIntent } }
  | { event: 'done'; data: { conversationId: string } }
  | { event: 'error'; data: { message: string } }
