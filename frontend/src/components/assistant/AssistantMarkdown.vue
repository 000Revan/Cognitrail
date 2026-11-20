<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { renderAssistantMarkdown } from '../../utils/assistantMarkdown'

const props = defineProps<{ content: string }>()
const router = useRouter()
const html = computed(() => renderAssistantMarkdown(props.content))

function openLink(event: MouseEvent) {
  if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  const anchor = event.target instanceof Element ? event.target.closest('a') : null
  const href = anchor?.getAttribute('href')
  if (!href || !href.startsWith('/') || href.startsWith('//')) return
  event.preventDefault()
  void router.push(href)
}
</script>

<template>
  <!-- HTML 只来自禁用原始 HTML 的 Markdown 渲染器。 -->
  <!-- eslint-disable vue/no-v-html -->
  <div
    class="assistant-markdown"
    @click="openLink"
    v-html="html"
  />
  <!-- eslint-enable vue/no-v-html -->
</template>

<style scoped>
.assistant-markdown { min-width: 0; overflow-wrap: anywhere; line-height: 1.85; }
.assistant-markdown :deep(> :first-child) { margin-top: 0; }
.assistant-markdown :deep(> :last-child) { margin-bottom: 0; }
.assistant-markdown :deep(p) { margin: 0 0 12px; }
.assistant-markdown :deep(h1), .assistant-markdown :deep(h2), .assistant-markdown :deep(h3),
.assistant-markdown :deep(h4), .assistant-markdown :deep(h5), .assistant-markdown :deep(h6) {
  margin: 22px 0 10px; font-size: 1.08em; line-height: 1.6; font-weight: 650;
}
.assistant-markdown :deep(h1), .assistant-markdown :deep(h2) { font-size: 1.18em; }
.assistant-markdown :deep(ul), .assistant-markdown :deep(ol) { margin: 10px 0 16px; padding-left: 1.6em; }
.assistant-markdown :deep(li) { margin: 6px 0; }
.assistant-markdown :deep(li > p) { margin-bottom: 6px; }
.assistant-markdown :deep(li > ul), .assistant-markdown :deep(li > ol) { margin-block: 4px; }
.assistant-markdown :deep(a) { color: var(--green); text-decoration: underline; text-underline-offset: 3px; }
.assistant-markdown :deep(a:hover) { text-decoration-thickness: 2px; }
.assistant-markdown :deep(a:focus-visible) { outline: 2px solid var(--green); outline-offset: 3px; border-radius: 2px; }
.assistant-markdown :deep(code) { padding: 2px 5px; border-radius: 4px; background: #1b30280a; font-family: Consolas, monospace; font-size: .9em; }
.assistant-markdown :deep(pre) { max-width: 100%; overflow-x: auto; padding: 14px 16px; border: 1px solid var(--line); border-radius: 8px; background: var(--paper); line-height: 1.65; }
.assistant-markdown :deep(pre code) { padding: 0; background: none; white-space: pre; overflow-wrap: normal; }
.assistant-markdown :deep(blockquote) { margin: 14px 0; padding: 4px 14px; border-left: 3px solid var(--green); color: var(--muted); }
.assistant-markdown :deep(blockquote > :last-child) { margin-bottom: 0; }
.assistant-markdown :deep(table) { display: block; max-width: 100%; overflow-x: auto; margin: 14px 0; border-collapse: collapse; font-size: .92em; }
.assistant-markdown :deep(th), .assistant-markdown :deep(td) { border: 1px solid var(--line); padding: 8px 12px; text-align: left; }
.assistant-markdown :deep(th) { background: var(--green-soft); }
.assistant-markdown :deep(hr) { border: 0; border-top: 1px solid var(--line); margin: 20px 0; }
</style>
