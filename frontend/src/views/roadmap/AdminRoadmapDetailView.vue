<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { adminRoadmapDetail, disableRoadmap, restoreRoadmap } from '../../api/roadmap'
import type { RoadmapDetail } from '../../types/roadmap'
import { difficultyName, formatDate } from '../../domain/roadmap'
import { useAuthStore } from '../../stores/auth'
import RoadmapContentReader from '../../components/roadmap/RoadmapContentReader.vue'
import AppDialog from '../../components/common/AppDialog.vue'
import AppIcon from '../../components/common/AppIcon.vue'
const route = useRoute(), auth = useAuthStore()
const data = ref<RoadmapDetail | null>(null), releaseId = ref('')
const loading = ref(false), error = ref(''), action = ref<'disable' | 'restore' | null>(null)
const reason = ref(''), busy = ref(false), actionError = ref('')
let request = 0
async function load() {
  const ticket = ++request, viewer = auth.sessionVersion
  data.value = null; loading.value = true; error.value = ''
  try {
    const result = await adminRoadmapDetail(String(route.params.id), releaseId.value || undefined)
    if (ticket === request && viewer === auth.sessionVersion) { data.value = result; releaseId.value = result.releaseId || '' }
  } catch (cause) { if (ticket === request && viewer === auth.sessionVersion) error.value = cause instanceof Error ? cause.message : '审核内容加载失败' }
  finally { if (ticket === request) loading.value = false }
}
function openAction(value: 'disable' | 'restore') { action.value = value; reason.value = ''; actionError.value = '' }
async function submit() {
  if (!data.value || !action.value || busy.value) return
  const ticket = request, viewer = auth.sessionVersion, selected = action.value
  busy.value = true; actionError.value = ''
  try {
    await (selected === 'disable' ? disableRoadmap : restoreRoadmap)(data.value.id, data.value.editVersion, reason.value.trim())
    if (ticket !== request || viewer !== auth.sessionVersion) return
    action.value = null; await load()
  } catch (cause) { if (ticket === request && viewer === auth.sessionVersion) actionError.value = cause instanceof Error ? cause.message : '操作失败，请重试' }
  finally { if (viewer === auth.sessionVersion) busy.value = false }
}
watch([() => route.params.id, () => auth.sessionVersion], () => { releaseId.value = ''; action.value = null; busy.value = false; void load() }, { immediate: true })
onBeforeUnmount(() => { request++ })
</script>

<template>
  <section
    class="admin-page admin-review"
    :aria-busy="loading"
  >
    <nav
      class="admin-breadcrumb"
      aria-label="面包屑"
    >
      <RouterLink to="/admin/roadmaps">社区路线管理</RouterLink><span>/</span><span>审核详情</span>
    </nav>
    <p
      v-if="loading"
      role="status"
    >
      正在读取发布内容…
    </p>
    <p
      v-if="error"
      role="alert"
      class="form-error"
    >
      {{ error }} <button
        class="text-button"
        @click="load"
      >
        重新加载
      </button>
    </p>
    <template v-if="data">
      <header class="admin-panel review-overview">
        <div class="review-heading">
          <div>
            <p class="admin-eyebrow">
              CONTENT REVIEW
            </p><h1>{{ data.title }}</h1><p>作者：{{ data.author.nickname || data.author.username }} · {{ difficultyName(data.difficulty) }} · {{ data.displayStatus }}</p>
          </div><button
            :class="data.status === 'disabled' ? 'primary-button' : 'danger-button'"
            @click="openAction(data.status === 'disabled' ? 'restore' : 'disable')"
          >
            {{ data.status === 'disabled' ? '恢复路线' : '下架路线' }}
          </button>
        </div>
        <p class="review-description">
          {{ data.description }}
        </p>
        <div class="review-version">
          <label>审核版本 <select
            v-model="releaseId"
            :disabled="loading || busy"
            @change="load"
          ><option
            v-for="release in data.releases"
            :key="release.id"
            :value="release.id"
          >V{{ release.versionNo }} · {{ formatDate(release.publishedAt) }}</option></select></label><span>{{ data.stageCount }} 个阶段 · {{ data.nodeCount }} 个节点</span>
        </div>
        <details class="review-release-note">
          <summary>版本说明</summary><p>{{ data.updateSummary || '暂无版本说明' }}</p>
        </details>
      </header>
      <p class="admin-footer-note review-notice">
        <AppIcon name="shield" />审核视图读取冻结发布内容，不产生收藏或学习记录。
      </p>
      <RoadmapContentReader
        :stages="data.stages"
        :connections="data.connections"
      />
      <section class="admin-panel review-history">
        <h2>治理记录</h2><p
          v-if="!data.moderationHistory?.length"
          class="muted"
        >
          这条路线暂未发生治理操作。
        </p><ol v-else>
          <li
            v-for="entry in data.moderationHistory"
            :key="entry.id"
          >
            <div><strong>{{ entry.action === 'disable' ? '下架路线' : '恢复路线' }}</strong><time>{{ formatDate(entry.createdAt) }}</time></div><p>{{ entry.reason }}</p><small>操作管理员 #{{ entry.actorId }}</small>
          </li>
        </ol>
      </section>
    </template>
    <AppDialog
      v-if="action && data"
      :title="action === 'disable' ? '下架这条路线？' : '恢复这条路线？'"
      :busy="busy"
      @close="action = null"
    >
      <form
        id="moderation-form"
        class="account-form"
        @submit.prevent="submit"
      >
        <p>{{ action === 'disable' ? '下架将限制所有发布版本的正文与资源访问，已有学习历史会保留。' : '恢复平台治理状态。作者归档、账号停用和单独版本限制仍按各自规则生效。' }}</p><label for="moderation-reason">{{ action === 'disable' ? '下架原因' : '恢复原因' }}</label><textarea
          id="moderation-reason"
          v-model="reason"
          required
          maxlength="1000"
          rows="4"
          :disabled="busy"
          placeholder="填写处理依据，便于追溯此次操作"
        /><p
          v-if="actionError"
          role="alert"
          class="form-error"
        >
          {{ actionError }}
        </p>
      </form>
      <template #footer>
        <button
          class="outline-link"
          :disabled="busy"
          @click="action = null"
        >
          取消
        </button><button
          type="submit"
          form="moderation-form"
          :class="action === 'disable' ? 'danger-button' : 'primary-button'"
          :disabled="busy || !reason.trim()"
        >
          {{ busy ? '正在处理…' : action === 'disable' ? '确认下架' : '确认恢复' }}
        </button>
      </template>
    </AppDialog>
  </section>
</template>

<style scoped>
.review-overview{padding:28px 32px}.review-heading{display:flex;align-items:center;justify-content:space-between;gap:20px}.review-heading h1{font-size:26px;margin:10px 0 12px;overflow-wrap:anywhere}.review-heading>div>p:last-child{font-size:12px;color:var(--admin-muted)}.review-heading>button{flex-shrink:0}.review-description{font-size:14px;line-height:1.8;color:#61796b;white-space:pre-wrap;overflow-wrap:anywhere;border-top:1px solid var(--admin-line);padding-top:20px;margin-top:24px}.review-version{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap;font-size:12px;color:var(--admin-muted);margin:24px 0 12px}.review-version label{display:flex;align-items:center;gap:12px}.review-version select{height:38px;max-width:240px;border:1px solid var(--admin-line);border-radius:8px;background:#fff;color:#435f4d;padding:0 12px}.review-release-note{font-size:12px;line-height:1.8;color:var(--admin-muted)}.review-release-note summary{cursor:pointer;min-height:32px}.review-release-note p{white-space:pre-wrap;overflow-wrap:anywhere}.review-notice{margin-block:20px}.review-history{margin-top:24px;padding:24px 28px}.review-history h2{font-size:16px;margin-top:0}.review-history>p{font-size:13px}.review-history ol{list-style:none;padding:0;margin:0}.review-history li{padding:20px 0;border-top:1px solid var(--admin-line)}.review-history li>div{display:flex;justify-content:space-between;font-size:13px;gap:12px}.review-history time,.review-history small{font-size:11px;color:var(--admin-muted)}.review-history li p{font-size:13px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:760px){.review-overview{padding:20px}.review-heading{align-items:flex-start;flex-direction:column}.review-heading h1{font-size:22px}.review-version label{flex-wrap:wrap}.review-version select{max-width:180px}.review-notice{line-height:1.8;align-items:flex-start}.review-notice svg{flex-shrink:0}.review-history{padding:20px}.review-history li>div{flex-wrap:wrap}}
@media(max-width:760px){.admin-review :deep(.content-reader-layout){grid-template-columns:minmax(0,1fr);height:auto;min-height:0}.admin-review :deep(.content-reader-directory){max-height:300px}.admin-review :deep(.content-reader-main){min-height:460px}.admin-review :deep(.reader-content-body){padding:22px 18px}.admin-review :deep(.reader-resource-cards){grid-template-columns:minmax(0,1fr)}.admin-review :deep(.reader-resource-cards li){padding:14px;gap:10px}.admin-review :deep(.reader-content-body h2){font-size:23px}}
@media(max-width:760px){.admin-review :deep(.reader-node-navigation){flex-wrap:wrap;padding:16px;gap:8px}.admin-review :deep(.reader-node-navigation button){flex:1;min-width:110px;padding:10px;font-size:12px;white-space:nowrap}.admin-review :deep(.reader-node-navigation>span){order:2;width:100%;text-align:center}}
</style>
