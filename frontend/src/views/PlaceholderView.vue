<script setup lang="ts">
import { useRoute } from 'vue-router'
import AppIcon from '../components/common/AppIcon.vue'

const route = useRoute()
</script>

<template>
  <section class="content-page">
    <header class="page-heading">
      <p class="eyebrow">
        COGNITRAIL
      </p>
      <h1>{{ route.meta.title }}</h1>
      <p>{{ route.meta.description }}</p>
    </header>
    <div
      class="feature-placeholder"
      role="status"
    >
      <span class="placeholder-icon"><AppIcon :name="String(route.meta.icon || 'repository')" /></span>
      <h2>页面正在准备中</h2>
      <RouterLink to="/">探索社区路线</RouterLink>
    </div>
  </section>
</template>
