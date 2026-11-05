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
      <h2>公开社区正在升级</h2>
      <p>此入口暂未开放。你可以先使用社区发现、路线创作、学习和问题反馈，其他功能完成验证后将逐步恢复。</p>
      <RouterLink to="/environment">查看运行状态</RouterLink>
    </div>
  </section>
</template>
