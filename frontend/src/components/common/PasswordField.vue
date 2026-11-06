<script setup lang="ts">
import { ref } from 'vue'
import FieldError from './FieldError.vue'

const model = defineModel<string>({ required: true })
defineProps<{ id: string; label: string; autocomplete: string; hint?: string; error?: string }>()
defineEmits<{ blur: [] }>()
const visible = ref(false)

function normalize(value: string) { return value.replace(/\s/g, '') }
function update(event: Event) {
  const input = event.target as HTMLInputElement
  input.value = normalize(input.value)
  model.value = input.value
}
function paste(event: ClipboardEvent) {
  if (!event.clipboardData) return
  event.preventDefault()
  const input = event.target as HTMLInputElement
  const start = input.selectionStart ?? input.value.length
  const end = input.selectionEnd ?? start
  const inserted = normalize(event.clipboardData.getData('text'))
  input.value = (input.value.slice(0, start) + inserted + input.value.slice(end)).slice(0, 30)
  model.value = input.value
  const position = Math.min(start + inserted.length, input.value.length)
  input.setSelectionRange(position, position)
}
</script>

<template>
  <div class="form-field">
    <label :for="id">{{ label }}</label>
    <div class="password-control">
      <input
        :id="id"
        :value="model"
        :type="visible ? 'text' : 'password'"
        :autocomplete="autocomplete"
        minlength="6"
        maxlength="30"
        :aria-describedby="error ? id + '-error' : hint ? id + '-hint' : undefined"
        :aria-invalid="error ? true : undefined"
        required
        @blur="$emit('blur')"
        @input="update"
        @paste="paste"
      >
      <button
        type="button"
        class="password-toggle"
        :aria-label="(visible ? '隐藏' : '显示') + label"
        :aria-pressed="visible"
        @click="visible = !visible"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        ><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle
          cx="12"
          cy="12"
          r="3"
        /><path
          v-if="!visible"
          d="m3 3 18 18"
        /></svg>
      </button>
    </div>
    <FieldError :id="id + '-error'" :message="error" />
    <p
      v-if="hint && !error"
      :id="id + '-hint'"
      class="field-hint"
    >
      {{ hint }}
    </p>
  </div>
</template>
