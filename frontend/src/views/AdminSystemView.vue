<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { http } from '../api/http'
import type { ApiResponse } from '../types/common'
import { useAuthStore } from '../stores/auth'
import AppIcon from '../components/common/AppIcon.vue'
import AppDialog from '../components/common/AppDialog.vue'
import { ElMessage } from 'element-plus'
import { formatDate } from '../domain/roadmap'
const auth = useAuthStore()
const info = ref<{ appName: string; timezone: string; sessionSeconds: number; loginLimit: number; loginWindowSeconds: number; outboxEnabled: boolean; outboxMaxAttempts: number; deliveryCounts: Record<string, number>; failedDeliveries: { id: string; eventType: string; attempts: number; errorType: string | null; updatedAt: string }[] } | null>(null)
const error = ref(''), loading = ref(false)
const checkinId = ref(''), checkinReason = ref(''), confirming = ref(false), saving = ref(false), checkinError = ref('')
async function invalidate() {
  if (saving.value) return
  const viewer = auth.sessionVersion
  saving.value = true; checkinError.value = ''
  try { await http.post('/api/v1/admin/checkins/' + checkinId.value + '/invalidate', { reason: checkinReason.value.trim(), expectedValid: true }); if (viewer !== auth.sessionVersion) return; confirming.value = false; checkinId.value = checkinReason.value = ''; ElMessage({ message: '打卡已撤销，有效打卡统计已更新。', type: 'success', duration: 3000 }) }
  catch (cause) { if (viewer === auth.sessionVersion) checkinError.value = cause instanceof Error ? cause.message : '撤销失败，请重试' }
  finally { if (viewer === auth.sessionVersion) saving.value = false }
}
let request = 0
async function load() {
  const ticket = ++request, viewer = auth.sessionVersion
  loading.value = true; error.value = ''; info.value = null
  try {
    const result = await http.get<ApiResponse<NonNullable<typeof info.value>>>('/api/v1/admin/system')
    if (ticket === request && viewer === auth.sessionVersion) info.value = result.data.data
  } catch (cause) { if (ticket === request && viewer === auth.sessionVersion) error.value = cause instanceof Error ? cause.message : '系统信息读取失败' }
  finally { if (ticket === request) loading.value = false }
}
watch(() => auth.sessionVersion, () => { confirming.value = saving.value = false; checkinId.value = checkinReason.value = checkinError.value = ''; void load() }, { immediate: true })
onBeforeUnmount(() => { request++ })
</script>
<template>
  <section class="admin-page">
    <header class="admin-page-heading">
      <div>
        <p class="admin-eyebrow">
          SYSTEM / CONFIGURATION
        </p><h1>系统设置</h1><p>查看当前生效的运行参数与消息投递状态。</p>
      </div><button
        class="outline-link"
        :disabled="loading"
        @click="load"
      >
        刷新信息
      </button>
    </header>
    <p
      v-if="loading"
      role="status"
    >
      正在读取系统信息…
    </p><p
      v-if="error"
      role="alert"
      class="form-error"
    >
      {{ error }} <button
        class="text-button"
        @click="load"
      >
        重试
      </button>
    </p>
    <template v-if="info">
      <section class="admin-panel system-section">
        <h2><AppIcon name="shield" />管理审计</h2><p class="system-hint">
          查看账号管理、内容治理及举报处理的操作记录。
        </p><RouterLink
          class="outline-link"
          to="/admin/system/audit"
        >查看操作审计</RouterLink>
      </section>
      <section class="admin-panel system-section">
        <h2><AppIcon name="settings" />基础与访问</h2><dl><div><dt>项目名称</dt><dd>{{ info.appName }}</dd></div><div><dt>业务时区</dt><dd>{{ info.timezone }}</dd></div><div><dt>登录有效期</dt><dd>{{ info.sessionSeconds / 60 }} 分钟</dd></div><div><dt>登录限流</dt><dd>{{ info.loginWindowSeconds }} 秒内 {{ info.loginLimit }} 次</dd></div></dl><p class="system-hint">
          以上参数由运行环境统一管理，本页只读展示。
        </p>
      </section>
      <section class="admin-panel system-section">
        <h2><AppIcon name="bell" />消息投递</h2><dl><div><dt>自动投递</dt><dd>{{ info.outboxEnabled ? '已启用' : '已关闭' }}</dd></div><div><dt>最大尝试次数</dt><dd>{{ info.outboxMaxAttempts }}</dd></div><div><dt>待处理</dt><dd>{{ info.deliveryCounts.pending || 0 }}</dd></div><div><dt>处理中</dt><dd>{{ info.deliveryCounts.processing || 0 }}</dd></div><div><dt>投递失败</dt><dd>{{ info.deliveryCounts.failed || 0 }}</dd></div><div><dt>已处理</dt><dd>{{ info.deliveryCounts.done || 0 }}</dd></div></dl>
        <details
          v-if="info.failedDeliveries?.length"
          class="delivery-failures"
        >
          <summary>最近的失败任务（最多 20 条）</summary><article
            v-for="task in info.failedDeliveries"
            :key="task.id"
          >
            <strong>#{{ task.id }} · {{ task.eventType }}</strong><p>已尝试 {{ task.attempts }} 次 · {{ task.errorType || '未知异常' }}</p><time>{{ formatDate(task.updatedAt) }}</time>
          </article>
        </details>
      </section>
    </template>
    <section class="admin-panel system-section">
      <h2><AppIcon name="clock" />打卡治理</h2><p class="system-hint">
        根据核实的打卡编号撤销无效事实，保留原记录并更新有效统计。此入口不提供他人学习详情查询。
      </p><form
        class="account-form"
        @submit.prevent="confirming = true; checkinError = ''"
      >
        <label for="checkin-id">打卡编号</label><input
          id="checkin-id"
          v-model="checkinId"
          required
          inputmode="numeric"
          pattern="[1-9][0-9]{0,18}"
          maxlength="19"
        ><label for="checkin-reason">撤销原因</label><textarea
          id="checkin-reason"
          v-model="checkinReason"
          required
          maxlength="1000"
          rows="3"
        /><button
          class="outline-link"
          :disabled="!checkinReason.trim() || !checkinId"
        >
          撤销无效打卡
        </button>
      </form>
    </section>
    <AppDialog
      v-if="confirming"
      title="确认撤销打卡？"
      :busy="saving"
      @close="confirming = false"
    >
      <p>打卡 #{{ checkinId }} 将标记为无效，记录保留，不能通过重新打卡恢复当天资格。</p><p>{{ checkinReason }}</p><p
        v-if="checkinError"
        class="form-error"
        role="alert"
      >
        {{ checkinError }}
      </p><template #footer>
        <button
          class="outline-link"
          :disabled="saving"
          @click="confirming = false"
        >
          取消
        </button><button
          class="danger-button"
          :disabled="saving"
          @click="invalidate"
        >
          {{ saving ? '正在处理…' : '确认撤销' }}
        </button>
      </template>
    </AppDialog>
  </section>
</template>
<style scoped>
.system-section{padding:28px 32px;margin-bottom:24px}.system-section h2{display:flex;align-items:center;gap:10px;font-size:16px;margin:0 0 24px}.system-section h2 svg{width:20px;color:#5c806a}.system-section dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 40px;margin:0}.system-section dl>div{display:flex;justify-content:space-between;gap:20px;padding:18px 0;border-top:1px solid var(--admin-line);font-size:13px}.system-section dt{color:var(--admin-muted)}.system-section dd{margin:0;overflow-wrap:anywhere}.system-hint{font-size:12px;color:var(--admin-muted);margin:24px 0 0;line-height:1.8}@media(max-width:760px){.system-section{padding:20px}.system-section dl{grid-template-columns:1fr}}
</style>
