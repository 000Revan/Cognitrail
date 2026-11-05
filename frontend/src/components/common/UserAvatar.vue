<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{ name: string; src?: string | null }>()
const failed = ref(false)
const imageSource = computed(() => {
  if (!props.src?.match(/^\/api\/v1\/users\/avatars\/[a-f0-9]{32}\.png$/)) return null
  return (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '') + props.src
})
watch(() => props.src, () => { failed.value = false })
</script>

<template>
  <span
    class="user-avatar"
    role="img"
    :aria-label="name + '的头像'"
  >
    <img
      v-if="imageSource && !failed"
      :src="imageSource"
      alt=""
      referrerpolicy="no-referrer"
      @error="failed = true"
    >
    <svg
      v-else
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="32"
        cy="24"
        r="10"
        fill="currentColor"
        opacity=".8"
      />
      <path
        d="M12 57a20 20 0 0 1 40 0"
        fill="currentColor"
        opacity=".8"
      />
    </svg>
  </span>
</template>
