<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps<{ title: string; busy?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()
let previous: HTMLElement | null = null
onMounted(() => {
  previous = document.activeElement as HTMLElement | null
  dialog.value?.showModal()
})
onBeforeUnmount(() => { dialog.value?.close(); previous?.focus() })
</script>

<template>
  <dialog
    ref="dialog"
    class="app-dialog"
    :aria-label="title"
    @cancel.prevent="!busy && emit('close')"
    @click="event => { if (event.target === dialog && !busy) emit('close') }"
  >
    <header>
      <h2>{{ title }}</h2><button
        type="button"
        aria-label="关闭对话框"
        :disabled="busy"
        @click="emit('close')"
      >
        ×
      </button>
    </header>
    <div class="dialog-body">
      <slot />
    </div>
    <footer v-if="$slots.footer">
      <slot name="footer" />
    </footer>
  </dialog>
</template>
