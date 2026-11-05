<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { register } from '../../api/auth'
import AuthLayout from '../../layouts/AuthLayout.vue'
import PasswordField from '../../components/common/PasswordField.vue'

const router = useRouter()
const username = ref('')
const nickname = ref('')
const password = ref('')
const confirmation = ref('')
const loading = ref(false)
const error = ref('')
async function submit() {
  if (loading.value) return
  error.value = ''
  if (password.value !== confirmation.value) { error.value = '两次输入的密码不一致'; return }
  if (!password.value.trim()) { error.value = '密码不能全为空白'; return }
  loading.value = true
  try {
    await register({ username: username.value, password: password.value, nickname: nickname.value || null })
    password.value = confirmation.value = ''
    await router.replace({ name: 'login', query: { reason: 'registered', username: username.value } })
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '注册失败，请稍后重试' }
  finally { loading.value = false }
}
</script>

<template>
  <AuthLayout>
    <p class="eyebrow">
      YOUR NEXT CHAPTER
    </p><h2 class="auth-title">
      创建你的账号
    </h2><p class="auth-subtitle">
      从学习者出发，也成为他人的引路人。
    </p>
    <form
      class="account-form"
      @submit.prevent="submit"
    >
      <fieldset :disabled="loading">
        <div class="form-field">
          <label for="register-username">用户名</label><input
            id="register-username"
            v-model="username"
            autocomplete="username"
            minlength="3"
            maxlength="30"
            pattern="[A-Za-z0-9_]+"
            required
            aria-describedby="username-hint"
          ><p
            id="username-hint"
            class="field-hint"
          >
            3–30 位字母、数字或下划线，统一使用小写。
          </p>
        </div>
        <div class="form-field">
          <label for="register-nickname">昵称 <span class="optional-label">选填</span></label><input
            id="register-nickname"
            v-model="nickname"
            autocomplete="nickname"
            maxlength="50"
            placeholder="希望大家怎么称呼你"
          >
        </div>
        <PasswordField
          id="register-password"
          v-model="password"
          label="密码"
          autocomplete="new-password"
          hint="6–30 位，自动去除空格。"
        />
        <PasswordField
          id="register-confirmation"
          v-model="confirmation"
          label="确认密码"
          autocomplete="new-password"
        />
        <p
          v-if="error"
          class="form-error"
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
          创建账号
        </ElButton>
      </fieldset>
    </form>
    <p class="auth-switch">
      已经有账号？<RouterLink to="/login">去登录 →</RouterLink>
    </p>
  </AuthLayout>
</template>
