<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { http } from '../api/http'
import type { ApiResponse, Page } from '../types/common'
import { useAuthStore } from '../stores/auth'
import { formatDate } from '../domain/roadmap'
interface Entry { id: string; actorId: string | null; action: string; targetType: string; targetId: string | null; result: string; createdAt: string; details: Record<string, unknown> }
const auth = useAuthStore(), items = ref<Entry[]>([]), total = ref(0), page = ref(1), loading = ref(false), error = ref('')
let generation = 0
async function load() {
  const ticket = ++generation, viewer = auth.sessionVersion
  items.value = []; loading.value = true; error.value = ''
  try { const result = (await http.get<ApiResponse<Page<Entry>>>('/api/v1/admin/system/audit-logs', { params: { page: page.value } })).data.data; if (ticket !== generation || viewer !== auth.sessionVersion) return; items.value = result.items; total.value = result.total }
  catch (cause) { if (ticket === generation) error.value = cause instanceof Error ? cause.message : '审计记录加载失败' }
  finally { if (ticket === generation) loading.value = false }
}
watch(() => auth.sessionVersion, () => { page.value = 1; total.value = 0; void load() }, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>
<template>
  <section class="admin-page">
    <nav class="admin-breadcrumb">
      <RouterLink to="/admin/system">系统设置</RouterLink><span>/</span><span>操作审计</span>
    </nav><header class="admin-page-heading">
      <div>
        <p class="admin-eyebrow">
          SYSTEM / AUDIT LOG
        </p><h1>操作审计</h1><p>核对管理操作、处理依据与变更记录。</p>
      </div><button
        class="outline-link"
        :disabled="loading"
        @click="load"
      >
        刷新记录
      </button>
    </header><div class="admin-panel audit-records">
      <p
        v-if="loading"
        role="status"
      >
        正在加载审计记录…
      </p><p
        v-if="error"
        class="form-error"
        role="alert"
      >
        {{ error }}
      </p><p v-if="!loading && !error && !items.length">
        暂无审计记录。
      </p><article
        v-for="entry in items"
        :key="entry.id"
      >
        <div><strong>{{ entry.action }}</strong><span>{{ entry.result === 'success' ? '成功' : '失败' }}</span></div><p>{{ entry.actorId ? '管理员 #' + entry.actorId : '系统' }} · {{ entry.targetType }} {{ entry.targetId ? '#' + entry.targetId : '' }}</p><dl v-if="Object.keys(entry.details).length">
          <div
            v-for="(value, key) in entry.details"
            :key="key"
          >
            <dt>{{ key }}</dt><dd>{{ typeof value === 'object' ? JSON.stringify(value) : value }}</dd>
          </div>
        </dl><time>{{ formatDate(entry.createdAt) }}</time>
      </article><footer>
        <span>共 {{ total }} 条 · 第 {{ page }} 页</span><button
          class="outline-link"
          :disabled="loading || page <= 1"
          @click="page--; load()"
        >
          上一页
        </button><button
          class="outline-link"
          :disabled="loading || page * 20 >= total"
          @click="page++; load()"
        >
          下一页
        </button>
      </footer>
    </div>
  </section>
</template>
<style scoped>
.audit-records>p,.audit-records article,.audit-records footer{padding:24px 28px}.audit-records article{border-bottom:1px solid var(--admin-line)}.audit-records article>div{display:flex;justify-content:space-between;gap:20px;font-size:14px}.audit-records article>div>span{font-size:12px;color:#528565}.audit-records p{font-size:13px;color:#6d8275;line-height:1.8}.audit-records time{font-size:11px;color:#8d9c93}.audit-records dl{font-size:12px;line-height:1.8;background:#f5f8f6;padding:12px 16px;border-radius:8px}.audit-records dl>div{display:flex;gap:16px}.audit-records dd{margin:0;overflow-wrap:anywhere}.audit-records dt{min-width:50px;color:#85978c}.audit-records footer{display:flex;justify-content:flex-end;align-items:center;gap:12px;font-size:12px;flex-wrap:wrap}.audit-records footer>span{margin-right:auto}
</style>
