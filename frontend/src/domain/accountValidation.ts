import { nextTick, reactive, ref, watch, type Ref } from 'vue'
import { ApiError } from '../api/http'

type Field = 'username' | 'password' | 'nickname' | 'confirmation'
export function useAccountValidation(fields: Partial<Record<Field, Ref<string>>>, prefix: string) {
  const errors = reactive<Partial<Record<Field, string>>>({})
  const touched = new Set<Field>()
  const error = ref('')
  function validate(field: Field) {
    const value = fields[field]?.value || ''
    let message = ''
    if (field === 'username') {
      const username = value.trim()
      if (!username) message = '请输入用户名'
      else if (username.length < 3 || username.length > 30) message = '用户名长度应为 3–30 位'
      else if (!/^[A-Za-z0-9_]+$/.test(username)) message = '用户名仅支持字母、数字和下划线'
    } else if (field === 'nickname') {
      if (value.length > 50) message = '昵称不能超过 50 位'
    } else {
      const password = value.replace(/\s/g, '')
      if (!password) message = field === 'confirmation' ? '请再次输入密码' : '请输入密码'
      else if (password.length < 6 || password.length > 30) message = '密码长度应为 6–30 位'
      else if (field === 'confirmation' && value !== fields.password?.value) message = '两次输入的密码不一致'
    }
    errors[field] = message
  }
  function blur(field: Field) { touched.add(field); validate(field) }
  const names = Object.keys(fields) as Field[]
  for (const field of names) watch(fields[field]!, () => {
    error.value = ''
    if (touched.has(field) || errors[field]) validate(field)
    if (field === 'password' && touched.has('confirmation')) validate('confirmation')
  }, { flush: 'sync' })
  function focusError() {
    const first = names.find(field => errors[field])
    if (first) void nextTick(() => document.getElementById(prefix + '-' + first)?.focus())
  }
  function validateAll() {
    error.value = ''
    names.forEach(blur)
    focusError()
    return !names.some(field => errors[field])
  }
  function reject(cause: unknown, fallback: string) {
    if (cause instanceof ApiError) {
      if (cause.errorCode === 'USERNAME_EXISTS' && fields.nickname) {
        errors.username = cause.message; touched.add('username'); focusError(); return
      }
      if (cause.errorCode === 'VALIDATION_ERROR' && Array.isArray(cause.details)) {
        let mapped = false
        let unmapped = false
        for (const detail of cause.details) {
          const field = Array.isArray(detail?.path) ? detail.path[detail.path.length - 1] as Field : undefined
          if (!field || !fields[field]) { unmapped = true; continue }
          validate(field)
          if (!errors[field]) errors[field] = field === 'username' ? '用户名应为 3–30 位字母、数字或下划线' : field === 'nickname' ? '昵称不能超过 50 位' : '密码长度应为 6–30 位'
          touched.add(field); mapped = true
        }
        if (mapped) { if (unmapped) error.value = cause.message; focusError(); return }
      }
    }
    error.value = cause instanceof Error ? cause.message : fallback
  }
  return { errors, error, blur, validateAll, reject }
}
