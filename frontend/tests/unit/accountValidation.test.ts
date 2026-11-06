import { effectScope, ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { ApiError } from '../../src/api/http'
import { useAccountValidation } from '../../src/domain/accountValidation'

describe('account field validation', () => {
  it('blocks empty submission and clears corrected field errors', () => {
    const scope = effectScope()
    scope.run(() => {
      const username = ref(''), password = ref('')
      const form = useAccountValidation({ username, password }, 'login')
      expect(form.validateAll()).toBe(false)
      expect(form.errors.username).toBe('请输入用户名')
      expect(form.errors.password).toBe('请输入密码')
      username.value = 'test_user'; password.value = 'abcdef'
      expect(form.errors.username).toBe('')
      expect(form.validateAll()).toBe(true)
    })
    scope.stop()
  })
  it('rechecks confirmation when the password changes', () => {
    const scope = effectScope()
    scope.run(() => {
      const password = ref('abcdef'), confirmation = ref('abcdef')
      const form = useAccountValidation({ password, confirmation }, 'register')
      form.blur('confirmation')
      password.value = 'ghijkl'
      expect(form.errors.confirmation).toBe('两次输入的密码不一致')
      confirmation.value = 'ghijkl'
      expect(form.errors.confirmation).toBe('')
    })
    scope.stop()
  })
  it('maps duplicate names and field validation responses while preserving login errors', () => {
    const scope = effectScope()
    scope.run(() => {
      const form = useAccountValidation({ username: ref('test_user'), nickname: ref(''), password: ref('abcdef') }, 'register')
      form.reject(new ApiError('该用户名已被使用', 409, 'USERNAME_EXISTS'), '')
      expect(form.errors.username).toBe('该用户名已被使用')
      form.reject(new ApiError('请求字段校验失败', 422, 'VALIDATION_ERROR', undefined, [{ path: ['body', 'password'], type: 'too_short' }]), '')
      expect(form.errors.password).toBe('密码长度应为 6–30 位')
      form.reject(new ApiError('账号或密码错误', 401, 'LOGIN_FAILED'), '')
      expect(form.error.value).toBe('账号或密码错误')
    })
    scope.stop()
  })
})
