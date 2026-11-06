<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthLayout from '../../layouts/AuthLayout.vue'
import PasswordField from '../../components/common/PasswordField.vue'
import FieldError from '../../components/common/FieldError.vue'
import { useAccountValidation } from '../../domain/accountValidation'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const username = ref(typeof route.query.username === 'string' ? route.query.username : '')
const password = ref('')
const loading = ref(false)
const { errors, error, blur, validateAll, reject } = useAccountValidation({ username, password }, 'login')
const notice = computed(() => ({ registered: '注册成功，登录后开始你的路线探索。', passwordChanged: '密码已修改，请使用新密码重新登录。', expired: '登录已结束，请重新登录。' })[String(route.query.reason) as 'registered' | 'passwordChanged' | 'expired'] || '')

async function submit() {
  if (loading.value) return
  if (!validateAll()) return
  loading.value = true
  try {
    const accepted = await auth.login({ username: username.value, password: password.value })
    password.value = ''
    if (accepted) await router.replace(auth.isAdmin ? '/admin/roadmaps' : '/')
  } catch (cause) {
    reject(cause, '登录失败，请稍后重试')
  } finally { loading.value = false }
}
</script>

<template>
  <AuthLayout>
    <p class="eyebrow">
      WELCOME BACK
    </p><h2 class="auth-title">
      欢迎回到知途工坊
    </h2><p class="auth-subtitle">
      普通用户登录后进入社区首页，管理员进入管理后台。
    </p>
    <p
      v-if="notice"
      class="form-notice"
      role="status"
    >
      {{ notice }}
    </p>
    <form
      class="account-form"
      novalidate
      @submit.prevent="submit"
    >
      <fieldset :disabled="loading">
        <div class="form-field">
          <label for="login-username">用户名</label><input
            id="login-username"
            v-model="username"
            :aria-invalid="errors.username ? true : undefined"
            :aria-describedby="errors.username ? 'login-username-error' : undefined"
            @blur="blur('username')"
            autocomplete="username"
            minlength="3"
            maxlength="30"
            pattern="[A-Za-z0-9_]+"
            required
            placeholder="输入你的用户名"
          >
          <FieldError id="login-username-error" :message="errors.username" />
        </div>
        <PasswordField
          id="login-password"
          v-model="password"
          :error="errors.password"
          @blur="blur('password')"
          label="密码"
          autocomplete="current-password"
        />
        <p
          class="field-error form-submit-error"
          role="alert"
        >
          {{ error }}
        </p>
        <ElButton
          class="submit-button"
          type="primary"
          native-type="submit"
          :loading="loading"
        >
          登录
        </ElButton>
      </fieldset>
    </form>
    <p class="auth-switch">
      还没有账号？<RouterLink to="/register">加入社区 →</RouterLink>
    </p>
    <p class="session-note">
      登录状态仅在当前页面保存，刷新后需要重新登录。
    </p>
  </AuthLayout>
</template>
