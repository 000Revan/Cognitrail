<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { enrollmentSummary, studyRecords, learningSessions } from '../../api/enrollment'
import { useAuthStore } from '../../stores/auth'
import type { EnrollmentSummary, StudyRecordPage } from '../../types/enrollment'
import type { Page } from '../../types/common'
const route = useRoute()
const auth = useAuthStore()
const summary = ref<EnrollmentSummary | null>(null)
const data = ref<StudyRecordPage | null>(null)
const versions = ref<Page<EnrollmentSummary> | null>(null)
const versionPage = ref(1)
const page = ref(1)
const error = ref('')
const loading = ref(false)
const pages = computed(() => Math.max(1, Math.ceil((data.value?.total || 0) / 20)))
const versionPages = computed(() => Math.max(1, Math.ceil((versions.value?.total || 0) / 20)))
let generation = 0
async function load() {
  const ticket = ++generation
  data.value = null; summary.value = null; error.value = ''; loading.value = true
  versions.value = null
  if (!auth.authenticated) { loading.value = false; return }
  try {
    const [metadata, records, history] = await Promise.all([enrollmentSummary(String(route.params.id)), studyRecords(String(route.params.id), page.value), learningSessions(String(route.params.id), versionPage.value)])
    if (ticket === generation) { summary.value = metadata; data.value = records; versions.value = history }
  } catch (cause) { if (ticket === generation) error.value = cause instanceof Error ? cause.message : '打卡记录加载失败' }
  finally { if (ticket === generation) loading.value = false }
}
watch([() => route.params.id, () => auth.user?.id, () => auth.sessionVersion], () => { page.value = 1; versionPage.value = 1; void load() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++ })
</script>
<template>
  <section class="content-page learning-history-page">
    <h1>路线打卡记录</h1><p>北京时间日期事实，退出与版本变化不删除已有记录。</p>
    <p
      v-if="loading"
      role="status"
    >
      正在加载…
    </p>
    <p
      v-if="error"
      role="alert"
      class="form-error"
    >
      {{ error }} <button
        type="button"
        class="text-button"
        @click="load"
      >
        重新加载
      </button>
    </p>
    <template v-if="summary && data">
      <h2>{{ summary.title }}</h2>
      <div class="route-actions">
        <RouterLink
          :to="{ name: 'learning-content', params: { id: summary.id } }"
          class="outline-link"
        >返回学习内容</RouterLink><RouterLink
          to="/dashboard"
          class="outline-link"
        >本人打卡日历</RouterLink>
      </div>
      <p>累计 {{ data.total }} 次 · {{ data.today }} {{ data.checkedInToday ? '已打卡' : '未打卡' }}</p>
      <ul class="route-record-list">
        <li
          v-for="item in data.items"
          :key="item.id"
        >
          <time>{{ item.checkinDate }}</time> · {{ item.isValid ? '有效打卡' : '已被治理撤销' }}
        </li>
      </ul>
      <p v-if="!data.items.length">
        暂无打卡记录。
      </p>
      <footer
        v-if="data.total"
        class="route-pagination"
      >
        <button
          type="button"
          class="outline-link"
          :disabled="page <= 1"
          @click="page--; load()"
        >
          上一页
        </button><span>{{ page }} / {{ pages }}</span>
        <button
          type="button"
          class="outline-link"
          :disabled="page >= pages"
          @click="page++; load()"
        >
          下一页
        </button>
      </footer>
      <section
        v-if="versions"
        id="version-history"
        aria-label="学习版本历史"
      >
        <h2>版本历史</h2><p>旧版本保留只读内容与进度，查看历史不会切换当前学习。</p>
        <ul class="learning-version-list">
          <li
            v-for="item in versions.items"
            :key="item.sessionId"
          >
            <strong>V{{ item.versionNo }} · {{ item.title }}</strong>
            <span> {{ item.isCurrentSession ? '当前学习' : '历史只读' }} · {{ item.completedNodeCount }} / {{ item.progressNodeCount }} · {{ item.progressPercent }}%</span>
            <RouterLink
              :to="{ name: 'learning-content', params: { id: item.id }, query: item.isCurrentSession ? {} : { session: item.sessionId } }"
              class="text-link"
            >{{ item.isCurrentSession ? '继续当前学习' : '回顾此版本' }}</RouterLink>
          </li>
        </ul>
        <footer
          v-if="versions.total > 20"
          class="route-pagination"
        >
          <button
            type="button"
            class="outline-link"
            :disabled="versionPage <= 1"
            @click="versionPage--; load()"
          >
            前一页版本
          </button>
          <span>{{ versionPage }} / {{ versionPages }}</span>
          <button
            type="button"
            class="outline-link"
            :disabled="versionPage >= versionPages"
            @click="versionPage++; load()"
          >
            后一页版本
          </button>
        </footer>
      </section>
    </template>
  </section>
</template>

<style scoped>
.learning-version-list { list-style: none; padding: 0; }
.learning-version-list li { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; padding: 18px 0; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
</style>
