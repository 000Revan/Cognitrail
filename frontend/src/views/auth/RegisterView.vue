<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { register } from '../../api/auth'
import AuthLayout from '../../layouts/AuthLayout.vue'
import PasswordField from '../../components/common/PasswordField.vue'
import FieldError from '../../components/common/FieldError.vue'
import { useAccountValidation } from '../../domain/accountValidation'

const router = useRouter()
const username = ref('')
const nickname = ref('')
const password = ref('')
const confirmation = ref('')
const loading = ref(false)
const { errors, error, blur, validateAll, reject } = useAccountValidation({ username, nickname, password, confirmation }, 'register')
async function submit() {
  if (loading.value) return
  if (!validateAll()) return
  loading.value = true
  try {
    await register({ username: username.value, password: password.value, nickname: nickname.value || null })
    password.value = confirmation.value = ''
    await router.replace({ name: 'login', query: { reason: 'registered', username: username.value } })
  } catch (cause) { reject(cause, '注册失败，请稍后重试') }
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
      novalidate
      @submit.prevent="submit"
    >
      <fieldset :disabled="loading">
        <div class="form-field">
          <label for="register-username">用户名</label><input
            id="register-username"
            v-model="username"
            :aria-invalid="errors.username ? true : undefined"
            :aria-describedby="errors.username ? 'register-username-error' : undefined"
            @blur="blur('username')"
            autocomplete="username"
            minlength="3"
            maxlength="30"
            pattern="[A-Za-z0-9_]+"
            required

          >
          <FieldError id="register-username-error" :message="errors.username" />
        </div>
        <div class="form-field">
          <label for="register-nickname">昵称 <span class="optional-label">选填</span></label><input
            id="register-nickname"
            v-model="nickname"
            :aria-invalid="errors.nickname ? true : undefined"
            :aria-describedby="errors.nickname ? 'register-nickname-error' : undefined"
            @blur="blur('nickname')"
            autocomplete="nickname"
            maxlength="50"
            placeholder="希望大家怎么称呼你"
          >
          <FieldError id="register-nickname-error" :message="errors.nickname" />
        </div>
        <PasswordField
          id="register-password"
          v-model="password"
          :error="errors.password"
          @blur="blur('password')"
          label="密码"
          autocomplete="new-password"
        />
        <PasswordField
          id="register-confirmation"
          v-model="confirmation"
          :error="errors.confirmation"
          @blur="blur('confirmation')"
          label="确认密码"
          autocomplete="new-password"
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
          创建账号
        </ElButton>
      </fieldset>
    </form>
    <p class="auth-switch">
      已经有账号？<RouterLink to="/login">去登录 →</RouterLink>
    </p>
  </AuthLayout>
</template>
