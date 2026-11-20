<script setup lang="ts">
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
function retrySession() { window.location.reload() }
</script>

<template>
  <ElConfigProvider
    :locale="zhCn"
  >
    <section
      v-if="auth.restoring || auth.restoreError"
      class="session-recovery"
      :aria-busy="auth.restoring"
    >
      <p
        v-if="auth.restoring"
        role="status"
      >
        正在恢复登录…
      </p>
      <template v-else>
        <p role="alert">
          {{ auth.restoreError }}
        </p>
        <ElButton
          type="primary"
          @click="retrySession"
        >
          重新尝试
        </ElButton>
      </template>
    </section>
    <RouterView v-else />
  </ElConfigProvider>
</template>

<style scoped>
.session-recovery { min-height: 100dvh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 24px; color: var(--muted); text-align: center; }
</style>
