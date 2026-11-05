<script setup lang="ts">
import { computed } from 'vue'
import { discussionTokens } from '../../domain/discussion'
const props = defineProps<{ text: string }>()
const tokens = computed(() => discussionTokens(props.text))
</script>

<template>
  <p class="discussion-text">
    <template
      v-for="(token, index) in tokens"
      :key="index"
    >
      <a
        v-if="token.kind === 'link'"
        :href="token.href"
        target="_blank"
        rel="noopener noreferrer nofollow ugc"
      >{{ token.text }}</a><strong v-else-if="token.kind === 'strong'">{{ token.text }}</strong><code v-else-if="token.kind === 'code'">{{ token.text }}</code><span v-else>{{ token.text }}</span>
    </template>
  </p>
</template>

<style scoped>
.discussion-text { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.9; }
.discussion-text a { color: var(--green); text-decoration: underline; text-underline-offset: 3px; }
.discussion-text code { background: var(--green-soft); padding: 2px 5px; border-radius: 4px; font-size: .9em; }
</style>
