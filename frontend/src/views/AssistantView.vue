<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import AppIcon from '../components/common/AppIcon.vue'
import AssistantMarkdown from '../components/assistant/AssistantMarkdown.vue'
import { getConversationMessages, getConversations, streamChat } from '../api/agent'
import type { AgentIntent, BusinessIntent, ChatMessage, ConversationSummary } from '../types/agent'

const collapsed = ref(window.matchMedia('(max-width: 760px)').matches)
const draft = ref('')
const composer = ref<HTMLTextAreaElement>()
const conversationElement = ref<HTMLElement>()
const conversations = ref<ConversationSummary[]>([])
const currentConversationId = ref<string | null>(null)
const messages = ref<(ChatMessage & { status?: 'streaming' | 'done' | 'error' })[]>([])
const generating = ref(false)
const loadingMessages = ref(false)
const loadingConversations = ref(false)
const keyword = ref('')
const errorMessage = ref('')
const intentHint = ref<BusinessIntent | null>(null)
const resolvedIntent = ref<AgentIntent | null>(null)
const generationText = computed(() => ({
  chat: '正在回答…', route_search: '正在查找路线…',
  route_create: '正在处理创作请求…', clarify: '正在确认需求…',
})[resolvedIntent.value || 'chat'])
const busy = computed(() => generating.value || loadingMessages.value)
const filteredConversations = computed(() => conversations.value.filter(
  item => item.title.toLowerCase().includes(keyword.value.trim().toLowerCase()),
))

function errorText(error: unknown) {
  return error instanceof Error ? error.message : '请求失败'
}

function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

async function scrollToBottom() {
  await nextTick()
  const element = conversationElement.value
  if (element) element.scrollTop = element.scrollHeight
}

async function loadConversations() {
  loadingConversations.value = true
  try {
    conversations.value = await getConversations()
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    loadingConversations.value = false
  }
}

async function selectConversation(id: string) {
  if (busy.value) return
  loadingMessages.value = true
  errorMessage.value = ''
  try {
    const detail = await getConversationMessages(id)
    currentConversationId.value = detail.id
    messages.value = detail.messages.map(item => ({ ...item, status: 'done' }))
    draft.value = ''
    intentHint.value = null
    void scrollToBottom()
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    loadingMessages.value = false
  }
}

/** 快捷入口只填入提问，不模拟尚未接入的模型响应。 */
async function prepareQuestion(text: string, intent: BusinessIntent) {
  if (busy.value) return
  draft.value = text
  intentHint.value = intent
  await nextTick()
  composer.value?.focus()
}

function newConversation() {
  if (busy.value) return
  currentConversationId.value = null
  messages.value = []
  errorMessage.value = ''
  draft.value = ''
  intentHint.value = null
  composer.value?.focus()
}

async function sendMessage() {
  const question = draft.value.trim()
  if (!question || busy.value) return
  generating.value = true
  resolvedIntent.value = null
  errorMessage.value = ''
  draft.value = ''
  const createdAt = new Date().toISOString()
  messages.value.push({ id: crypto.randomUUID(), role: 'user', content: question, createdAt })
  messages.value.push({ id: crypto.randomUUID(), role: 'assistant', content: '', createdAt, status: 'streaming' })
  const answer = messages.value[messages.value.length - 1]!
  let completed = false
  void scrollToBottom()
  try {
    await streamChat({ message: question, conversationId: currentConversationId.value, intentHint: intentHint.value }, event => {
      if (event.event === 'conversation') currentConversationId.value = event.data.conversationId
      else if (event.event === 'reset') answer.content = ''
      else if (event.event === 'intent') resolvedIntent.value = event.data.resolvedIntent
      else if (event.event === 'delta') {
        answer.content += event.data.text
        void scrollToBottom()
      } else if (event.event === 'done') {
        completed = true
        currentConversationId.value = event.data.conversationId
        answer.status = 'done'
      } else {
        answer.status = 'error'
        errorMessage.value = event.data.message
      }
    })
    if (completed && currentConversationId.value) {
      try {
        const detail = await getConversationMessages(currentConversationId.value)
        messages.value = detail.messages.map(item => ({ ...item, status: 'done' }))
      } catch (error) {
        errorMessage.value = `回答已完成，历史同步失败：${errorText(error)}`
      }
    }
  } catch (error) {
    answer.status = 'error'
    errorMessage.value = errorText(error)
  } finally {
    // 包括首次失败留下的空会话，列表仍与后端保持一致。
    await loadConversations()
    generating.value = false
    void scrollToBottom()
    await nextTick()
    composer.value?.focus()
  }
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void sendMessage()
  }
}

onMounted(() => { void loadConversations() })
</script>

<template>
  <section
    class="assistant-page"
    aria-label="工坊助手"
  >
    <div
      class="assistant-shell"
      :class="{ 'history-collapsed': collapsed }"
    >
      <aside
        v-if="!collapsed"
        id="assistant-history"
        class="assistant-history"
        aria-label="历史对话"
      >
        <div class="history-heading">
          <h2>历史对话</h2>
          <button
            class="icon-control"
            type="button"
            aria-label="收起历史对话"
            aria-controls="assistant-history"
            :aria-expanded="true"
            @click="collapsed = true"
          >
            <AppIcon name="arrow" />
          </button>
        </div>
        <el-button
          type="primary"
          class="new-conversation"
          :disabled="busy"
          @click="newConversation"
        >
          <span
            class="plus-mark"
            aria-hidden="true"
          >＋</span>新建对话
        </el-button>
        <div
          class="history-search"
        >
          <AppIcon name="search" />
          <input
            v-model="keyword"
            aria-label="搜索历史对话"
            placeholder="搜索历史对话"
          >
        </div>
        <div
          v-if="filteredConversations.length === 0"
          class="history-empty"
        >
          <AppIcon name="message" /><p>{{ loadingConversations ? '正在加载…' : keyword.trim() ? '没有找到相关对话' : '暂无历史对话' }}</p>
        </div>
        <div
          v-else
          class="history-list"
        >
          <button
            v-for="item in filteredConversations"
            :key="item.id"
            type="button"
            class="history-item"
            :class="{ active: currentConversationId === item.id }"
            :disabled="busy"
            :aria-current="currentConversationId === item.id ? 'true' : undefined"
            @click="selectConversation(item.id)"
          >
            <span class="history-title">{{ item.title }}</span>
            <time :datetime="item.updatedAt">{{ formatTime(item.updatedAt) }}</time>
          </button>
        </div>
      </aside>

      <div class="assistant-main">
        <header class="assistant-heading">
          <button
            v-if="collapsed"
            class="icon-control"
            type="button"
            aria-label="展开历史对话"
            aria-controls="assistant-history"
            :aria-expanded="false"
            @click="collapsed = false"
          >
            <AppIcon name="menu" />
          </button>
          <div><h1>工坊助手</h1><p>路线发现与创作助手</p></div>
          <button
            v-if="collapsed"
            class="compact-new"
            type="button"
            :disabled="busy"
            @click="newConversation"
          >
            新建对话
          </button>
        </header>
        <div
          ref="conversationElement"
          class="assistant-conversation"
          :aria-busy="busy"
          role="region"
          aria-label="对话内容"
          tabindex="0"
        >
          <div
            v-if="loadingMessages"
            class="conversation-loading"
          >
            正在加载对话…
          </div>
          <div
            v-else-if="messages.length === 0"
            class="assistant-welcome"
          >
            <div class="welcome-mark">
              <img
                src="/brand-mark.png"
                alt=""
                width="54"
                height="54"
              >
            </div>
            <h2>你好，今天想探索什么？</h2>
            <p>帮你发现合适的路线，也帮你整理创作思路。</p>
            <div class="welcome-actions">
              <el-button @click="prepareQuestion('帮我找一条适合我的学习路线。', 'route_search')">
                <AppIcon name="compass" />帮我找路线
              </el-button>
              <el-button @click="prepareQuestion('帮我设计一条学习路线。', 'route_create')">
                <AppIcon name="repository" />帮我创建路线
              </el-button>
            </div>
          </div>
          <div
            v-else
            class="message-list"
          >
            <article
              v-for="message in messages"
              :key="message.id"
              class="chat-message"
              :class="message.role"
            >
              <div class="message-role">
                {{ message.role === 'user' ? '你' : '工坊助手' }}
              </div>
              <AssistantMarkdown
                v-if="message.role === 'assistant' && message.content"
                :content="message.content"
              />
              <div
                v-else
                class="message-content"
              >
                {{ message.content || (message.status === 'streaming' ? '正在思考…' : '未生成回答') }}
              </div>
              <small v-if="message.status === 'error'">本轮未确认完成</small>
            </article>
          </div>
        </div>
        <div class="assistant-compose-area">
          <div class="assistant-composer">
            <div
              class="intent-options"
              aria-label="回答方向"
            >
              <button
                v-for="option in [{ value: 'route_search', label: '找路线' }, { value: 'route_create', label: '创作路线' }] as const"
                :key="option.value"
                type="button"
                :disabled="busy"
                :aria-pressed="intentHint === option.value"
                @click="intentHint = intentHint === option.value ? null : option.value"
              >
                {{ option.label }}{{ intentHint === option.value ? ' ×' : '' }}
              </button>
            </div>
            <textarea
              ref="composer"
              v-model="draft"
              :disabled="busy"
              aria-label="输入问题"
              placeholder="输入你的问题，或说说想找、想创建的路线…"
              maxlength="4000"
              rows="2"
              @keydown="handleComposerKeydown"
            />
            <div class="composer-toolbar">
              <span
                v-if="errorMessage"
                class="chat-error"
                role="alert"
              >{{ errorMessage }}</span>
              <span
                v-else-if="generating"
                class="generation-status"
              >{{ resolvedIntent ? generationText : '正在理解问题…' }}</span>
              <button
                class="send-button"
                type="button"
                :disabled="busy || !draft.trim()"
                aria-label="发送"
                @click="sendMessage"
              >
                <AppIcon name="arrow" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.assistant-page { height: calc(100dvh - 76px); min-height: 540px; padding: 24px 32px; }
.assistant-shell { display: grid; grid-template-columns: 250px minmax(0, 1fr); height: 100%; overflow: hidden; border: 1px solid var(--line); border-radius: var(--radius-card); background: var(--paper); }
.assistant-shell.history-collapsed { grid-template-columns: minmax(0, 1fr); }
.assistant-history { display: flex; flex-direction: column; min-height: 0; padding: 24px 20px 18px; background: var(--surface-soft); border-right: 1px solid var(--line); }
.history-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 22px; }
.history-heading h2 { font-size: 19px; margin: 0; }
.icon-control { display: inline-flex; justify-content: center; align-items: center; flex-shrink: 0; width: 36px; height: 36px; padding: 0; border: 0; border-radius: 6px; background: transparent; color: var(--muted); cursor: pointer; }
.icon-control:hover { background: var(--green-soft); color: var(--green); }
.new-conversation { width: 100%; height: 44px; }
.plus-mark { margin-right: 8px; font-size: 22px; }
.history-search { margin-top: 16px; display: flex; gap: 10px; align-items: center; padding: 10px 12px; border: 1px solid var(--line); border-radius: var(--radius-control); background: var(--paper); color: var(--muted); }
.history-search .app-icon { width: 18px; height: 18px; }
.history-search input { min-width: 0; width: 100%; border: 0; font: inherit; font-size: 13px; background: transparent; color: var(--muted); cursor: not-allowed; }
.history-empty { display: flex; flex: 1; flex-direction: column; align-items: center; justify-content: center; color: var(--muted); font-size: 13px; min-height: 100px; }
.history-empty .app-icon { width: 38px; height: 38px; opacity: .65; }
.history-empty p { margin: 14px 0; }
.assistant-main { min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.assistant-heading { display: flex; align-items: center; gap: 14px; margin: 0 28px; padding: 22px 0 18px; border-bottom: 1px solid var(--line); }
.assistant-heading h1 { margin: 0; font-size: 24px; line-height: 1.4; letter-spacing: 0; }
.assistant-heading p { margin: 6px 0 0; font-size: 13px; color: var(--muted); }
.assistant-conversation { flex: 1; min-height: 0; overflow-y: auto; padding: 28px; display: flex; }
.assistant-welcome { margin: auto; padding: 14px 0; text-align: center; max-width: 680px; }
.welcome-mark { display: inline-grid; place-items: center; width: 84px; height: 84px; border-radius: 18px; background: var(--green-soft); margin-bottom: 22px; }
.welcome-mark img { object-fit: contain; }
.assistant-welcome h2 { font-size: clamp(23px, 2.6vw, 34px); line-height: 1.5; margin: 0 0 12px; }
.assistant-welcome p { margin: 0; color: var(--muted); font-size: 15px; line-height: 1.8; }
.welcome-actions { display: flex; justify-content: center; flex-wrap: wrap; gap: 16px; margin-top: 30px; }
.welcome-actions .el-button { margin: 0; height: 44px; padding: 0 22px; color: var(--ink); }
.welcome-actions .app-icon { margin-right: 10px; color: var(--green); }
.assistant-compose-area { padding: 8px 28px 16px; }
.assistant-composer { border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px 12px; }
.assistant-composer:focus-within { border-color: var(--green); }
.intent-options { display: flex; gap: 8px; margin-bottom: 12px; }
.intent-options button { border: 1px solid var(--line); border-radius: 6px; padding: 4px 10px; background: transparent; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; }
.intent-options button[aria-pressed="true"] { background: var(--green-soft); border-color: var(--green); color: var(--green); }
.intent-options button:disabled { opacity: .6; cursor: default; }
.assistant-composer textarea { display: block; width: 100%; min-height: 48px; max-height: 140px; resize: none; border: 0; outline: none; background: transparent; font: inherit; font-size: 14px; line-height: 1.7; color: var(--ink); }
.assistant-composer textarea::placeholder { color: var(--muted); }
.composer-toolbar { display: flex; justify-content: flex-end; align-items: center; }
.send-button { display: grid; place-items: center; width: 38px; height: 38px; border: 0; border-radius: var(--radius-control); color: white; background: var(--green); }
.send-button:disabled { opacity: .5; cursor: not-allowed; }
.send-button .app-icon { transform: rotate(90deg); }
.history-search input { color: var(--ink); cursor: text; outline: none; }
.history-list { flex: 1; min-height: 0; margin-top: 16px; overflow-y: auto; }
.history-item { display: flex; flex-direction: column; gap: 8px; width: 100%; margin-bottom: 8px; padding: 12px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--ink); text-align: left; font: inherit; cursor: pointer; }
.history-item:hover, .history-item.active { border-color: var(--line); background: var(--paper); }
.history-item.active { color: var(--green); }
.history-item:disabled { cursor: default; }
.history-title { display: block; width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
.history-item time { color: var(--muted); font-size: 11px; }
.compact-new { margin-left: auto; padding: 8px 10px; border: 1px solid var(--line); border-radius: 6px; background: var(--paper); color: var(--ink); font: inherit; font-size: 12px; cursor: pointer; }
.compact-new:disabled { opacity: .5; cursor: not-allowed; }
.conversation-loading { margin: auto; color: var(--muted); font-size: 14px; }
.message-list { width: 100%; }
.chat-message { min-width: 0; max-width: 88%; margin-bottom: 22px; padding: 18px 22px; border-radius: 12px; }
.chat-message.user { margin-left: auto; background: var(--green-soft); }
.chat-message.assistant { margin-right: auto; background: var(--surface-soft); font-size: 15px; }
.message-role { margin-bottom: 8px; color: var(--muted); font-size: 12px; }
.message-content { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.8; }
.chat-message small { display: block; margin-top: 8px; color: var(--muted); }
.composer-toolbar { gap: 12px; }
.chat-error, .generation-status { flex: 1; font-size: 12px; }
.chat-error { color: #c45656; }
.generation-status { color: var(--muted); }
.send-button:not(:disabled) { cursor: pointer; }
@media(max-width: 1000px) { .assistant-page { padding: 20px; } .assistant-shell { grid-template-columns: 220px minmax(0, 1fr); } }
@media(max-width: 760px) {
  .assistant-page { height: calc(100dvh - 120px); min-height: 500px; padding: 12px; }
  .assistant-shell { position: relative; grid-template-columns: minmax(0, 1fr); }
  .assistant-history { position: absolute; inset: 0 auto 0 0; width: 240px; max-width: 82%; z-index: 2; box-shadow: 6px 0 18px #1b302812; }
  .assistant-heading { margin-inline: 16px; padding-block: 16px; }
  .assistant-heading h1 { font-size: 21px; }
  .assistant-conversation { padding: 20px 16px; }
  .chat-message { max-width: 100%; padding: 14px 16px; }
  .assistant-welcome p { font-size: 13px; }
  .welcome-mark { width: 64px; height: 64px; margin-bottom: 16px; }
  .welcome-actions { gap: 10px; margin-top: 22px; }
  .welcome-actions .el-button { padding-inline: 12px; }
  .assistant-compose-area { padding: 8px 14px 12px; }
}
</style>
