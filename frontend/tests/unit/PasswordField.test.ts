import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import PasswordField from '../../src/components/common/PasswordField.vue'

it('密码默认隐藏，可用键盘操作的按钮切换，不改变输入内容', async () => {
  const component = mount(PasswordField, { props: {
    modelValue: 'secret-password', id: 'test-password', label: '密码', autocomplete: 'new-password',
  } })
  expect(component.get('input').attributes('type')).toBe('password')
  expect(component.get('input').attributes('autocomplete')).toBe('new-password')
  expect(component.get('button').attributes('type')).toBe('button')
  await component.get('button').trigger('click')
  expect(component.get('input').attributes('type')).toBe('text')
  expect(component.get('button').attributes('aria-label')).toBe('隐藏密码')
  expect((component.get('input').element as HTMLInputElement).value).toBe('secret-password')
})

it('密码输入限制为6至30位，移除首尾和中间空白并同步可见内容', async () => {
  const component = mount(PasswordField, { props: {
    modelValue: '', id: 'password', label: '密码', autocomplete: 'new-password',
  } })
  expect(component.get('input').attributes('minlength')).toBe('6')
  expect(component.get('input').attributes('maxlength')).toBe('30')
  await component.get('input').setValue(' ab c\td e f\u3000 ')
  expect(component.emitted('update:modelValue')?.at(-1)).toEqual(['abcdef'])
  expect((component.get('input').element as HTMLInputElement).value).toBe('abcdef')
})

it('去除空格后密码未变化时也清理输入框，粘贴先去空白再限制长度', async () => {
  const component = mount(PasswordField, { props: {
    modelValue: 'abcdef', id: 'password', label: '密码', autocomplete: 'new-password',
  } })
  const input = component.get('input')
  await input.setValue(' ab cd ef ')
  expect((input.element as HTMLInputElement).value).toBe('abcdef')
  ;(input.element as HTMLInputElement).setSelectionRange(0, 6)
  await input.trigger('paste', { clipboardData: { getData: () => ' ' + 'a '.repeat(30) } })
  expect(component.emitted('update:modelValue')?.at(-1)).toEqual(['a'.repeat(30)])
  expect((input.element as HTMLInputElement).value).toBe('a'.repeat(30))
})
