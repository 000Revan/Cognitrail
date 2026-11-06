<script setup lang="ts">
defineProps<{ id: string; message?: string }>()
</script>

<template>
  <p v-if="message" :id="id" class="field-error field-error-slot" role="alert">
    {{ message }}
  </p>
</template>
