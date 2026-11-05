<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useHealthStore } from '../stores/health'
import type { CheckStatus } from '../types/health'

const health = useHealthStore()
const allReady = computed(() => health.live.status === 'success' && health.ready.status === 'success')
const labels: Record<CheckStatus, string> = { idle: '待检查', checking: '检查中', success: '已就绪', error: '未就绪' }
const cards = computed(() => [
  { key: 'live', number: '01', title: '应用服务', caption: '前端 → FastAPI', result: health.live },
  { key: 'ready', number: '02', title: '数据库与迁移', caption: 'FastAPI → MySQL', result: health.ready },
])

onMounted(() => health.refresh())
</script>

<template>
  <div class="overview">
    <section class="intro">
      <p class="eyebrow">
        <span /> EVERY STEP COUNTS
      </p>
      <h1>让学习<span>有迹可循。</span></h1>
      <p class="intro-description">
        一条清晰的路线，一次专注的学习。<br>知途工坊，从连接好每个起点开始。
      </p>
      <div
        class="intro-path"
        aria-hidden="true"
      >
        <span>目标</span><i /><span>路线</span><i /><span>行动</span><i /><span class="path-end">成长</span>
      </div>
    </section>

    <section
      aria-labelledby="connection-title"
      class="connection-section"
    >
      <div class="section-heading">
        <div>
          <p class="small-label">
            FOUNDATION CHECK
          </p><h2 id="connection-title">
            基础连接检查
          </h2>
        </div>
        <ElButton
          :loading="health.loading"
          class="refresh-button"
          @click="health.refresh()"
        >
          {{ health.loading ? '正在检查' : '重新检查' }}<span
            v-if="!health.loading"
            aria-hidden="true"
          > ↗</span>
        </ElButton>
      </div>
      <div
        class="check-grid"
        aria-live="polite"
        :aria-busy="health.loading"
      >
        <article
          v-for="card in cards"
          :key="card.key"
          class="check-card"
          :data-testid="card.key + '-card'"
        >
          <div class="check-top">
            <span class="check-number">{{ card.number }}</span><span
              class="status-label"
              :class="card.result.status"
            ><i />{{ labels[card.result.status] }}</span>
          </div>
          <h3>{{ card.title }}</h3><p class="check-caption">
            {{ card.caption }}
          </p>
          <p class="check-message">
            {{ card.result.message }}
          </p>
          <p
            v-if="card.result.requestId"
            class="request-id"
          >
            请求编号：{{ card.result.requestId }}
          </p>
        </article>
      </div>
      <div
        class="check-summary"
        role="status"
      >
        <span
          class="summary-dot"
          :class="{ complete: allReady }"
        /><p>{{ health.loading ? '正在验证真实服务连接，请稍候。' : allReady ? '基础环境已就绪，可以开始本阶段的启动验收。' : '请确认后端已启动，并检查数据库配置和迁移状态。' }}</p><time v-if="health.checkedAt">更新于 {{ health.checkedAt }}</time>
      </div>
    </section>

    <section
      class="next-section"
      aria-labelledby="stage-title"
    >
      <div class="stage-marker">
        R07
      </div>
      <div class="stage-copy">
        <p class="small-label">
          当前开发阶段
        </p><h2 id="stage-title">
          从问题反馈，到路线持续改进。
        </h2><p>账号、创作、发现、学习与版本升级已逐步开放。本阶段接入路线话题、回复及站内通知，开发与自动联调完成，待用户验收；作者主页和路线治理仍在后续计划中。</p>
      </div>
      <div class="stage-detail">
        <span>当前范围</span><strong>路线讨论与站内通知</strong><span>下一阶段</span><strong>举报与内容治理</strong>
      </div>
    </section>

    <section
      v-if="health.databaseInfo"
      class="environment-detail"
      aria-label="已验证环境信息"
    >
      <span>MySQL {{ health.databaseInfo.databaseVersion }}</span><span>迁移 {{ health.databaseInfo.migrationRevision }}</span><span>业务时区 {{ health.databaseInfo.timezone }}</span>
    </section>
  </div>
</template>
