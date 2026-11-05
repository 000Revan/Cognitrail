<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { adminRoadmaps } from '../../api/roadmap'
import type { RoadmapSummary } from '../../types/roadmap'
import { difficultyName, formatDate } from '../../domain/roadmap'
import { useAuthStore } from '../../stores/auth'
import AppIcon from '../../components/common/AppIcon.vue'
import UserAvatar from '../../components/common/UserAvatar.vue'

const auth = useAuthStore()
const keyword = ref(''), difficulty = ref(''), status = ref(''), sortBy = ref('publishedAt'), order = ref('desc')
const page = ref(1), total = ref(0), items = ref<RoadmapSummary[]>([]), loading = ref(false), error = ref('')
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / 12)))
let request = 0
async function load() {
  const ticket = ++request, viewer = auth.sessionVersion
  loading.value = true; error.value = ''; items.value = []
  try {
    const result = await adminRoadmaps({ keyword: keyword.value.trim(), difficulty: difficulty.value || undefined,
      status: status.value || undefined, sortBy: sortBy.value, order: order.value, page: page.value })
    if (ticket !== request || viewer !== auth.sessionVersion) return
    total.value = result.total; items.value = result.items
    if (!items.value.length && page.value > 1) { page.value--; await load() }
  } catch (cause) { if (ticket === request && viewer === auth.sessionVersion) error.value = cause instanceof Error ? cause.message : '路线加载失败，请重试' }
  finally { if (ticket === request) loading.value = false }
}
function filter() { page.value = 1; void load() }
function reset() { keyword.value = difficulty.value = status.value = ''; sortBy.value = 'publishedAt'; order.value = 'desc'; filter() }
function turn(value: number) { page.value = value; void load() }
watch(() => auth.sessionVersion, () => { total.value = 0; page.value = 1; void load() }, { immediate: true })
onBeforeUnmount(() => { request++ })
</script>

<template>
  <section
    class="admin-page admin-roadmaps"
    :aria-busy="loading"
  >
    <header class="admin-page-heading">
      <div>
        <p class="admin-eyebrow">
          COMMUNITY / CONTENT MANAGEMENT
        </p><h1>社区路线管理</h1><p>查看社区发布内容，让每一条学习路径都值得信任。</p>
      </div><div class="admin-count">
        符合条件的路线 <strong>{{ total }}</strong> 条
      </div>
    </header>
    <div class="admin-panel">
      <form
        class="admin-filters"
        aria-label="筛选社区路线"
        @submit.prevent="filter"
      >
        <label class="admin-search-field"><span>路线搜索</span><div><AppIcon name="search" /><input
          v-model="keyword"
          placeholder="搜索已发布路线标题"
          maxlength="200"
          aria-label="搜索路线标题"
        ></div></label>
        <label><span>难度</span><select
          v-model="difficulty"
          aria-label="难度"
          @change="filter"
        ><option value="">全部难度</option><option value="beginner">入门</option><option value="intermediate">进阶</option><option value="advanced">高级</option></select></label>
        <label><span>状态</span><select
          v-model="status"
          aria-label="状态"
          @change="filter"
        ><option value="">全部状态</option><option value="published">已发布</option><option value="archived">作者归档</option><option value="disabled">已下架</option></select></label>
        <label><span>排序依据</span><select
          v-model="sortBy"
          aria-label="排序依据"
          @change="filter"
        ><option value="publishedAt">发布时间</option><option value="updatedAt">管理更新时间</option><option value="title">路线标题</option></select></label>
        <label><span>顺序</span><select
          v-model="order"
          aria-label="顺序"
          @change="filter"
        ><option value="desc">降序</option><option value="asc">升序</option></select></label>
        <button
          type="submit"
          class="primary-button"
        >
          搜索
        </button><button
          type="button"
          class="admin-reset"
          @click="reset"
        >
          重置
        </button>
      </form>
      <div class="admin-table-caption">
        <h2>路线列表</h2><button
          class="admin-refresh"
          :disabled="loading"
          @click="load"
        >
          <AppIcon name="refresh" />刷新列表
        </button>
      </div>
      <p
        v-if="loading"
        role="status"
        class="admin-list-state"
      >
        正在加载路线…
      </p>
      <div
        v-else-if="error"
        role="alert"
        class="admin-list-state form-error"
      >
        {{ error }} <button
          class="text-button"
          @click="load"
        >
          重新加载
        </button>
      </div>
      <div
        v-else-if="!items.length"
        class="admin-empty"
      >
        <AppIcon name="repository" /><h3>没有符合条件的路线</h3><p>可以调整搜索词、难度或状态后再试。</p><button
          class="outline-link"
          @click="reset"
        >
          清除筛选
        </button>
      </div>
      <p
        v-if="!loading && !error && items.length"
        class="admin-mobile-table-hint"
      >
        左右滑动表格可查看完整信息与审核入口。
      </p>
      <div
        v-if="!loading && !error && items.length"
        class="admin-table-wrap"
        tabindex="0"
        role="region"
        aria-label="社区路线表格，可横向滚动"
      >
        <table class="admin-table">
          <thead>
            <tr>
              <th scope="col">
                路线名称
              </th><th scope="col">
                作者
              </th><th scope="col">
                难度
              </th><th scope="col">
                状态
              </th><th scope="col">
                发布时间
              </th><th scope="col">
                <span class="sr-only">操作</span>
              </th>
            </tr>
          </thead><tbody>
            <tr
              v-for="item in items"
              :key="item.id"
            >
              <td>
                <RouterLink
                  class="admin-route-name"
                  :to="'/admin/roadmaps/' + item.id"
                ><span class="admin-route-icon"><AppIcon name="repository" /></span><span><strong>{{ item.title }}</strong><small>V{{ item.versionNo }} <span>·</span> {{ item.stageCount }} 个阶段 <span>·</span> {{ item.nodeCount }} 个节点</small></span></RouterLink>
              </td><td><span class="admin-table-author"><UserAvatar :name="item.author.nickname || item.author.username" /><span>{{ item.author.nickname || item.author.username }}</span></span></td><td>
                <span
                  class="admin-difficulty"
                  :class="item.difficulty"
                >{{ difficultyName(item.difficulty) }}</span>
              </td><td>
                <span
                  class="admin-content-status"
                  :class="item.status"
                ><i />{{ item.displayStatus }}</span>
              </td><td class="admin-date">
                {{ formatDate(item.publishedAt || item.updatedAt) }}
              </td><td>
                <RouterLink
                  class="admin-review-link"
                  :to="'/admin/roadmaps/' + item.id"
                >审核详情 <span aria-hidden="true">↗</span></RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="admin-pagination">
        <span>每页 12 条 · 共 {{ total }} 条</span><div>
          <button
            aria-label="上一页"
            :disabled="loading || page <= 1"
            @click="turn(page - 1)"
          >
            ‹
          </button><span>{{ page }} / {{ pageCount }}</span><button
            aria-label="下一页"
            :disabled="loading || page >= pageCount"
            @click="turn(page + 1)"
          >
            ›
          </button>
        </div>
      </footer>
    </div>
    <p class="admin-footer-note">
      <AppIcon name="shield" />仅展示曾发布的社区路线，未发布工作稿由作者独立管理。
    </p>
  </section>
</template>

<style scoped>
.admin-filters{display:flex;align-items:flex-end;gap:12px;padding:24px;flex-wrap:wrap;background:#fff}.admin-filters label{display:grid;gap:8px;min-width:108px}.admin-filters label>span{font-size:12px;font-weight:500;color:#586e63}.admin-filters input,.admin-filters select{height:42px;border:1px solid #dce5df;border-radius:8px;background:#fff;font:inherit;font-size:13px;color:#344e41;padding:0 12px;min-width:0}.admin-filters select{cursor:pointer}.admin-search-field{flex:1;min-width:210px!important}.admin-search-field>div{position:relative}.admin-search-field svg{position:absolute;left:12px;top:12px;width:18px;height:18px;color:#82958b}.admin-search-field input{width:100%;padding-left:38px}.admin-filters button{min-height:42px;padding:0 18px;font-size:13px}.admin-reset{background:transparent;border:0;color:#687c73;cursor:pointer}.admin-table-caption{display:flex;align-items:center;justify-content:space-between;padding:18px 24px;border-top:1px solid #edf1ee}.admin-table-caption h2{font-size:15px;margin:0}.admin-refresh{display:flex;align-items:center;gap:6px;min-height:36px;background:transparent;border:0;color:#687c73;font-size:12px;cursor:pointer}.admin-refresh svg{width:15px;height:15px}.admin-table-wrap{overflow-x:auto}.admin-table{width:100%;border-collapse:collapse;text-align:left;font-size:13px;white-space:nowrap}.admin-table th{font-size:11px;font-weight:500;color:#7d8e85;background:#f8faf9;padding:14px 20px;border-block:1px solid #edf1ee}.admin-table td{padding:20px;border-bottom:1px solid #edf1ee}.admin-table th:first-child,.admin-table td:first-child{padding-left:24px;width:38%;white-space:normal;min-width:240px}.admin-table tbody tr{transition:background .18s}.admin-table tbody tr:hover{background:#fafcfb}.admin-route-name{display:flex;align-items:center;gap:14px}.admin-route-name strong{display:block;font-size:14px;line-height:1.6;font-weight:600;overflow-wrap:anywhere}.admin-route-name:hover strong{color:#21694f}.admin-route-name small{display:block;font-size:11px;color:#8a998f;margin-top:5px}.admin-route-name small span{margin:0 5px}.admin-route-icon{display:grid;place-items:center;width:42px;height:46px;flex-shrink:0;border-radius:10px;background:#edf4ef;color:#6b917a}.admin-route-icon svg{width:20px}.admin-table-author{display:flex;align-items:center;gap:8px;max-width:160px;white-space:normal;overflow-wrap:anywhere}.admin-table-author :deep(.user-avatar){width:28px;height:28px;flex-shrink:0}.admin-difficulty{font-size:11px;border:1px solid #e2e8e4;padding:4px 9px;border-radius:6px;background:#fafcfb;color:#657e70}.admin-difficulty.intermediate{background:#f7f2e9;color:#876b3e;border-color:#eee5d4}.admin-difficulty.advanced{background:#f2eef7;color:#77628c;border-color:#e6deed}.admin-content-status{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:#4d8362}.admin-content-status i{width:6px;height:6px;border-radius:50%;background:currentColor}.admin-content-status.disabled{color:#b75d54}.admin-content-status.archived{color:#8b908c}.admin-date{color:#7d8e85;font-size:12px}.admin-review-link{color:#21694f;font-size:12px;display:inline-flex;gap:12px;align-items:center;min-height:44px}.admin-pagination{display:flex;justify-content:space-between;align-items:center;padding:18px 24px;font-size:11px;color:#819087;gap:8px}.admin-pagination>div{display:flex;gap:14px;align-items:center}.admin-pagination button{width:36px;height:36px;border:1px solid #dfe7e1;background:#fff;border-radius:7px;color:#456754;cursor:pointer}.admin-pagination button:disabled{opacity:.4;cursor:default}.admin-list-state{padding:40px 24px;font-size:14px}.admin-empty{padding:64px 20px;text-align:center;color:#687c73}.admin-empty>svg{width:44px;height:44px;opacity:.55}.admin-empty h3{font-size:16px;color:#344e41}.admin-empty p{font-size:13px;margin-bottom:24px}
@media(max-width:760px){.admin-filters{padding:16px;gap:12px}.admin-filters label{flex:1;min-width:calc(50% - 12px)}.admin-search-field{flex-basis:100%}.admin-table-caption{padding:12px 16px}.admin-pagination{padding:14px 16px;flex-wrap:wrap}.admin-footer-note{align-items:flex-start;line-height:1.7}.admin-footer-note svg{flex-shrink:0;margin-top:3px}}
.admin-table{min-width:940px}.admin-table-author{min-width:140px}.admin-table td{vertical-align:middle}
.admin-mobile-table-hint{display:none}@media(max-width:760px){.admin-mobile-table-hint{display:block;margin:0;padding:0 16px 12px;font-size:11px;color:#7b8e81;line-height:1.6}}
</style>
