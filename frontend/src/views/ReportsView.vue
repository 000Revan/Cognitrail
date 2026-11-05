<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { reportList, reportDetail, handleReport, type Report } from '../api/moderation'
import { useAuthStore } from '../stores/auth'
import { formatDate } from '../domain/roadmap'
import AppDialog from '../components/common/AppDialog.vue'
import AppIcon from '../components/common/AppIcon.vue'
const route = useRoute(), auth = useAuthStore()
const admin = computed(() => route.name === 'admin-reports')
const status = ref(''), page = ref(1), total = ref(0), items = ref<Report[]>([]), loading = ref(false), error = ref('')
const selected = ref<Report | null>(null), choice = ref('processing'), action = ref('none'), reason = ref(''), busy = ref(false), actionError = ref('')
const labels: Record<string, string> = { pending: '待受理', processing: '处理中', resolved: '已处理', rejected: '未采纳' }
const kinds: Record<string, string> = { roadmap: '路线', issue: '话题', comment: '回复' }
const reasons: Record<string, string> = { spam: '垃圾广告', copyright: '侵权内容', abuse: '攻击与骚扰', unsafe: '违规或危险内容', other: '其他问题' }
const visibilityLabels: Record<string, string> = { public: '正常展示', normal: '正常展示', hidden: '已隐藏', disabled: '已下架', deleted: '已删除' }
const canHandle = computed(() => !!selected.value && ['pending', 'processing'].includes(selected.value.status))
const actionHint = computed(() => choice.value !== 'resolved' || action.value === 'none' ? '仅记录处理结论，不改变内容当前的展示状态。' : action.value === 'disable' ? '确认后将下架整条路线，保留已有学习记录与历史版本。' : action.value === 'hide' ? '确认后将隐藏该条内容，保留引用与处理记录。' : '恢复平台可见状态；作者撤回或其他访问限制仍然生效。')
const opening = ref(''), notice = ref('')
let generation = 0, detailRequest = 0
function closeReview() { if (busy.value) return; selected.value = null; detailRequest++; actionError.value = ''; reason.value = '' }
async function load() {
  const ticket = ++generation, viewer = auth.sessionVersion
  loading.value = true; error.value = ''; items.value = []
  try { const result = await reportList(admin.value, status.value, page.value); if (ticket !== generation || viewer !== auth.sessionVersion) return; items.value = result.items; total.value = result.total; if (!items.value.length && page.value > 1) { page.value--; await load() } }
  catch (cause) { if (ticket === generation) error.value = cause instanceof Error ? cause.message : '举报记录加载失败' }
  finally { if (ticket === generation) loading.value = false }
}
watch([() => auth.sessionVersion, () => route.fullPath], () => { selected.value = null; detailRequest++; busy.value = false; opening.value = ''; notice.value = ''; reason.value = ''; actionError.value = ''; page.value = 1; total.value = 0; void load() }, { immediate: true })
onBeforeUnmount(() => { generation++; detailRequest++ })
function filter() { page.value = 1; void load() }
async function open(item: Report) {
  const ticket = ++detailRequest, viewer = auth.sessionVersion
  actionError.value = ''; selected.value = null; error.value = ''; opening.value = item.id; notice.value = ''
  try { const result = await reportDetail(item.id); if (ticket !== detailRequest || viewer !== auth.sessionVersion) return; selected.value = result; choice.value = result.status === 'pending' ? 'processing' : 'resolved'; action.value = 'none'; reason.value = '' }
  catch (cause) { if (ticket === detailRequest && viewer === auth.sessionVersion) error.value = cause instanceof Error ? cause.message : '举报详情加载失败' }
  finally { if (ticket === detailRequest) opening.value = '' }
}
async function submit() {
  if (!selected.value || !canHandle.value || busy.value || !reason.value.trim()) return
  const ticket = detailRequest, viewer = auth.sessionVersion
  busy.value = true; actionError.value = ''
  try { await handleReport(selected.value.id, { expectedStatus: selected.value.status, status: choice.value, action: choice.value === 'resolved' ? action.value : 'none', reason: reason.value.trim() }); if (ticket !== detailRequest || viewer !== auth.sessionVersion) return; selected.value = null; reason.value = ''; notice.value = '处理结果已保存'; await load() }
  catch (cause) { if (ticket === detailRequest && viewer === auth.sessionVersion) actionError.value = cause instanceof Error ? cause.message : '处理失败，请重试' }
  finally { if (viewer === auth.sessionVersion) busy.value = false }
}
</script>
<template>
  <section
    class="reports-page"
    :class="admin ? 'admin-page' : 'content-page'"
  >
    <header class="admin-page-heading reports-heading">
      <div>
        <p
          v-if="admin"
          class="admin-eyebrow"
        >
          COMMUNITY / REPORTS
        </p><h1>{{ admin ? '举报处理' : '我的举报' }}</h1><p>{{ admin ? '核对内容与举报依据，记录每一次处理决定。' : '查看你提交的举报及处理结果。' }}</p>
      </div>
      <button
        type="button"
        class="outline-link reports-refresh"
        :disabled="loading || !!opening"
        @click="notice = ''; load()"
      >
        <AppIcon name="refresh" />刷新列表
      </button>
    </header>
    <p
      v-if="notice"
      role="status"
      class="reports-notice"
    >
      <AppIcon name="check" />{{ notice }}
    </p>
    <div class="admin-panel report-list">
      <header class="report-queue-heading">
        <div><h2>{{ admin ? '举报队列' : '举报记录' }}<span>{{ total }}</span></h2><p>{{ status ? labels[status] : '全部状态' }} · 按提交时间倒序</p></div><label class="report-status-filter">处理状态<select
          v-model="status"
          aria-label="举报处理状态"
          :disabled="loading"
          @change="notice = ''; filter()"
        ><option value="">全部状态</option><option
          v-for="(label, value) in labels"
          :key="value"
          :value="value"
        >{{ label }}</option></select></label>
      </header>
      <p
        v-if="loading"
        role="status"
        class="report-empty"
      >
        正在加载举报记录…
      </p>
      <p
        v-else-if="error"
        class="form-error report-load-error"
        role="alert"
      >
        {{ error }} <button
          type="button"
          class="text-button"
          @click="load"
        >
          重试
        </button>
      </p>
      <div
        v-else-if="!items.length"
        class="report-empty"
      >
        <AppIcon name="shield" /><h3>暂无举报记录</h3><p>{{ status ? '当前状态下没有举报，可以切换其他状态查看。' : admin ? '收到的举报将在这里展示。' : '提交后的举报将在这里展示。' }}</p>
      </div>
      <template v-else>
        <div
          class="report-column-labels"
          aria-hidden="true"
        >
          <span>举报内容</span><span>举报原因</span><span>提交时间</span><span>处理状态</span><span v-if="admin">操作</span>
        </div>
        <article
          v-for="item in items"
          :key="item.id"
          class="report-row"
        >
          <div class="report-row-top">
            <div class="report-subject">
              <span class="report-kind-icon"><AppIcon :name="item.targetType === 'roadmap' ? 'repository' : 'message'" /></span><div>
                <strong>{{ kinds[item.targetType] }} #{{ item.targetId }}</strong><small>举报 #{{ item.id }}</small><p
                  v-if="item.description"
                  class="report-description"
                >
                  {{ item.description }}
                </p><p
                  v-if="item.resultNote"
                  class="report-result"
                >
                  处理说明：{{ item.resultNote }}
                </p>
              </div>
            </div>
            <span class="report-reason">{{ reasons[item.reasonCode] }}</span>
            <time :datetime="item.createdAt">{{ formatDate(item.createdAt) }}</time>
            <span
              class="report-status"
              :data-status="item.status"
            ><i aria-hidden="true" />{{ labels[item.status] }}</span>
          </div>
          <div
            v-if="admin"
            class="report-row-foot"
          >
            <button
              type="button"
              class="outline-link review-entry"
              :disabled="!!opening || busy"
              @click="open(item)"
            >
              {{ opening === item.id ? '正在加载…' : ['pending', 'processing'].includes(item.status) ? '查看并处理' : '查看详情' }}<AppIcon name="chevron" />
            </button>
          </div>
        </article>
      </template>
      <footer class="report-pagination">
        <span>共 {{ total }} 条 · {{ page }} / {{ Math.max(1, Math.ceil(total / 20)) }}</span><div>
          <button
            type="button"
            class="outline-link"
            :disabled="loading || page <= 1"
            @click="page--; load()"
          >
            上一页
          </button><button
            type="button"
            class="outline-link"
            :disabled="loading || page * 20 >= total"
            @click="page++; load()"
          >
            下一页
          </button>
        </div>
      </footer>
    </div>
    <AppDialog
      v-if="selected"
      class="report-review-dialog"
      :title="canHandle ? '举报审核' : '处理详情'"
      :busy="busy"
      @close="closeReview"
    >
      <div class="review-context">
        <span>举报 #{{ selected.id }}</span><span
          class="report-status"
          :data-status="selected.status"
        ><i aria-hidden="true" />{{ labels[selected.status] }}</span>
      </div>
      <div class="review-layout">
        <div class="report-evidence">
          <section class="review-section">
            <h3><AppIcon name="flag" />举报信息</h3><dl class="report-facts">
              <div><dt>举报对象</dt><dd>{{ kinds[selected.targetType] }} #{{ selected.targetId }}</dd></div><div><dt>举报原因</dt><dd>{{ reasons[selected.reasonCode] }}</dd></div><div><dt>提交时间</dt><dd>{{ formatDate(selected.createdAt) }}</dd></div>
            </dl><div class="report-description-block">
              <h4>补充说明</h4><p>{{ selected.description || '举报人未补充说明' }}</p>
            </div>
          </section>
          <section class="review-section report-target">
            <header>
              <h3><AppIcon name="repository" />内容预览</h3><span
                v-if="selected.target"
                class="target-visibility"
              >{{ visibilityLabels[selected.target.visibility] || '状态未知' }}</span>
            </header><template v-if="selected.target">
              <h4>{{ selected.target.title }}</h4><p
                v-if="selected.target.body"
                class="report-target-body"
              >
                {{ selected.target.body }}
              </p><p
                v-else
                class="report-muted"
              >
                {{ selected.targetType === 'roadmap' ? '请进入路线审核页核对完整发布内容。' : '当前没有可展示的正文。' }}
              </p><RouterLink
                :to="'/admin/roadmaps/' + selected.target.roadmapId"
                class="review-route-link"
                @click="selected = null; detailRequest++"
              >审核路线发布内容 <AppIcon name="chevron" /></RouterLink>
            </template><p
              v-else
              class="report-muted"
            >
              目标已不可访问，原举报记录仍保留。
            </p>
          </section>
        </div>
        <form
          v-if="canHandle"
          id="handle-report-form"
          class="account-form review-form"
          @submit.prevent="submit"
        >
          <h3><AppIcon name="shield" />审核决定</h3><p class="review-form-description">
            请先核对左侧内容，再填写处理结论。
          </p>
          <fieldset :disabled="busy">
            <div class="form-field">
              <label for="report-choice">处理结果</label><select
                id="report-choice"
                v-model="choice"
              >
                <option value="processing">
                  受理并处理中
                </option><option value="resolved">
                  确认有效并结案
                </option><option value="rejected">
                  不采纳并结案
                </option>
              </select>
            </div>
            <div
              v-if="choice === 'resolved'"
              class="form-field"
            >
              <label for="report-action">内容操作</label><select
                id="report-action"
                v-model="action"
              >
                <option value="none">
                  保留现状，仅记录结论
                </option><option
                  v-if="selected.targetType === 'roadmap'"
                  value="disable"
                >
                  下架整条路线
                </option><option
                  v-else
                  :disabled="!selected.target || selected.target.visibility === 'deleted'"
                  value="hide"
                >
                  隐藏此内容，保留引用
                </option><option
                  :disabled="!selected.target || selected.target.visibility === 'deleted'"
                  value="restore"
                >
                  恢复平台可见状态
                </option>
              </select>
            </div>
            <div class="form-field">
              <label for="report-result">处理依据与说明</label><textarea
                id="report-result"
                v-model="reason"
                rows="5"
                required
                maxlength="1000"
                placeholder="说明核查事实、处理依据及结论，便于举报人了解结果。"
                aria-describedby="report-result-hint"
              /><p
                id="report-result-hint"
                class="report-input-hint"
              >
                <span>必填，此说明将展示给举报人</span><span>{{ reason.length }} / 1000</span>
              </p>
            </div>
            <p
              class="report-action-note"
              :class="{ 'has-content-action': choice === 'resolved' && action !== 'none' }"
            >
              <AppIcon name="shield" />{{ actionHint }}
            </p><p
              v-if="actionError"
              class="form-error"
              role="alert"
            >
              {{ actionError }}
            </p>
          </fieldset>
        </form>
        <section
          v-else
          class="review-section report-conclusion"
        >
          <h3><AppIcon name="check" />处理结论</h3><p>{{ selected.resultNote || '暂无处理说明' }}</p><p
            v-if="selected.handledAt"
            class="report-muted"
          >
            处理时间：{{ formatDate(selected.handledAt) }}
          </p>
        </section>
      </div>
      <template #footer>
        <span class="review-footer-hint">{{ canHandle ? '提交后保存处理结论及所选内容操作' : '该举报已结案' }}</span><button
          type="button"
          class="outline-link"
          :disabled="busy"
          @click="closeReview"
        >
          关闭
        </button><button
          v-if="canHandle"
          class="primary-button"
          type="submit"
          form="handle-report-form"
          :disabled="busy || !reason.trim()"
        >
          {{ busy ? '正在提交…' : '确认处理' }}
        </button>
      </template>
    </AppDialog>
  </section>
</template>
<style scoped>
.reports-page { max-width: 1440px; margin-inline: auto; }.reports-heading { gap: 24px; }.reports-refresh { display: inline-flex; align-items: center; justify-content: center; gap: 8px; flex-shrink: 0; }.reports-refresh .app-icon { width: 17px; height: 17px; }
.content-page .report-column-labels, .content-page .report-row { grid-template-columns: minmax(200px, 1fr) 130px 170px 90px; }
.admin-page .report-description { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.report-list { overflow: hidden; box-shadow: none; }.report-queue-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px; padding: 24px 28px; border-bottom: 1px solid var(--line); }.report-queue-heading h2 { display: flex; align-items: center; gap: 10px; font-size: 18px; margin: 0 0 8px; }.report-queue-heading h2 span { font-size: 13px; font-weight: 500; color: var(--muted); background: var(--green-soft); padding: 3px 9px; border-radius: 6px; }.report-queue-heading p { margin: 0; font-size: 13px; color: var(--muted); }.report-status-filter { display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--muted); }.report-status-filter select { min-height: 44px; padding: 0 34px 0 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--paper); color: var(--ink); }
.report-column-labels, .report-row { display: grid; grid-template-columns: minmax(200px, 1fr) 130px 170px 90px 126px; align-items: center; gap: 20px; padding: 20px 28px; }.report-column-labels { background: var(--green-soft); font-size: 12px; color: var(--muted); padding-block: 13px; }.report-row { border-bottom: 1px solid var(--line); }.report-row-top { display: contents; }.report-subject { display: flex; align-items: flex-start; gap: 12px; min-width: 0; }.report-kind-icon { width: 40px; height: 40px; border: 1px solid var(--line); border-radius: 10px; color: var(--green); background: var(--green-soft); display: grid; place-items: center; flex-shrink: 0; }.report-kind-icon .app-icon { width: 20px; height: 20px; }.report-subject > div { min-width: 0; }.report-subject strong { font-size: 15px; overflow-wrap: anywhere; }.report-subject small { display: block; font-size: 12px; color: var(--muted); margin-top: 5px; }.report-description, .report-result { font-size: 13px; line-height: 1.8; color: var(--muted); margin: 8px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }.report-result { border-left: 2px solid var(--line); padding-left: 10px; }.report-reason { font-size: 13px; }.report-row time { color: var(--muted); font-size: 12px; line-height: 1.7; }.report-status { display: inline-flex; align-items: center; gap: 6px; justify-self: start; font-size: 12px; color: var(--muted); background: var(--green-soft); border-radius: 6px; padding: 6px 9px; white-space: nowrap; }.report-status i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }.report-status[data-status=processing] { color: #27658b; background: #edf5fc; }.report-status[data-status=resolved] { color: var(--green); background: var(--green-soft); }.report-status[data-status=rejected] { color: #7a5738; background: #faf2e9; }.review-entry { white-space: nowrap; min-width: 128px; display: inline-flex; gap: 6px; align-items: center; justify-content: center; width: 126px; font-size: 13px; }.review-entry .app-icon, .review-route-link .app-icon { width: 16px; height: 16px; transform: rotate(-90deg); }.report-pagination { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 20px 28px; font-size: 13px; color: var(--muted); flex-wrap: wrap; }.report-pagination > div { display: flex; gap: 10px; }.report-empty { padding: 60px 24px; text-align: center; color: var(--muted); }.report-empty > .app-icon { width: 36px; height: 36px; color: var(--green); }.report-empty h3 { margin: 14px 0 8px; font-size: 17px; color: var(--ink); }.report-empty p { font-size: 14px; margin: 0; }.report-load-error { margin: 24px 28px; }.reports-notice { display: flex; align-items: center; gap: 10px; color: var(--green); padding: 12px 16px; background: var(--green-soft); border: 1px solid var(--line); border-radius: 8px; font-size: 14px; }.reports-notice .app-icon { width: 18px; height: 18px; }
.report-review-dialog { width: min(1060px, calc(100vw - 48px)); max-height: calc(100dvh - 48px); }.report-review-dialog[open] { display: flex; flex-direction: column; }.report-review-dialog :deep(> header), .report-review-dialog :deep(> footer) { flex-shrink: 0; padding: 18px 26px; }.report-review-dialog :deep(.dialog-body) { overflow-y: auto; min-height: 0; padding: 22px 26px 26px; }.review-context { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; color: var(--muted); font-size: 13px; }.review-layout { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); align-items: start; gap: 24px; }.report-evidence { display: grid; gap: 18px; min-width: 0; }.review-section { padding: 20px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); min-width: 0; }.review-section h3, .review-form h3 { display: flex; align-items: center; gap: 9px; font-size: 16px; margin: 0 0 18px; }.review-section h3 .app-icon, .review-form h3 .app-icon { width: 19px; height: 19px; color: var(--green); }.report-facts { margin: 0; display: grid; gap: 10px; font-size: 13px; }.report-facts > div { display: grid; grid-template-columns: 74px minmax(0,1fr); gap: 12px; }.report-facts dt { color: var(--muted); }.report-facts dd { margin: 0; overflow-wrap: anywhere; }.report-description-block { border-top: 1px solid var(--line); margin-top: 18px; padding-top: 15px; }.report-description-block h4 { font-size: 13px; color: var(--muted); font-weight: 400; margin: 0 0 8px; }.report-description-block p { font-size: 14px; margin: 0; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }.report-target > header { display: flex; align-items: flex-start; gap: 10px; justify-content: space-between; }.report-target h4 { font-size: 15px; line-height: 1.8; margin: 0 0 10px; overflow-wrap: anywhere; }.target-visibility { font-size: 12px; color: var(--muted); white-space: nowrap; }.report-target-body { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.9; max-height: 240px; overflow-y: auto; margin: 0 0 16px; }.report-muted { font-size: 13px; color: var(--muted); line-height: 1.8; }.review-route-link { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; color: var(--green); font-size: 13px; text-decoration: underline; text-underline-offset: 3px; }
.review-form.account-form { border: 1px solid var(--line); border-radius: 10px; padding: 20px; margin: 0; min-width: 0; background: var(--green-soft); }.review-form-description { margin: -8px 0 20px; font-size: 13px; color: var(--muted); line-height: 1.8; }.review-form fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }.review-form .form-field { margin-bottom: 18px; }.review-form label { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 14px; }.review-form select, .review-form textarea { display: block; box-sizing: border-box; width: 100%; border: 1px solid var(--line); border-radius: 8px; background: var(--paper); color: var(--ink); font: inherit; font-size: 14px; padding: 11px 12px; min-height: 44px; }.review-form textarea { min-height: 136px; resize: vertical; line-height: 1.8; }.review-form select:focus-visible, .review-form textarea:focus-visible, .report-status-filter select:focus-visible { outline: 2px solid var(--green); outline-offset: 2px; }.required-mark { color: var(--muted); font-size: 12px; font-weight: 400; }.report-input-hint { display: flex; justify-content: space-between; gap: 10px; margin: 7px 0 0; font-size: 12px; color: var(--muted); }.report-action-note { display: flex; align-items: flex-start; gap: 8px; border-top: 1px solid var(--line); padding-top: 16px; font-size: 13px; color: var(--muted); line-height: 1.8; margin: 0; }.report-action-note .app-icon { width: 18px; height: 18px; flex-shrink: 0; margin-top: 2px; }.report-action-note.has-content-action { color: #855121; }.review-footer-hint { margin-right: auto; color: var(--muted); font-size: 12px; align-self: center; }.report-conclusion p { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.9; }
@media(max-width: 1100px) { .report-column-labels, .report-row { grid-template-columns: minmax(160px, 1fr) 100px 130px 82px 116px; gap: 12px; padding-inline: 20px; }.review-entry { width: 116px; } }
@media(max-width: 900px) { .report-column-labels { display: none; }.report-row { display: block; padding: 22px; }.report-row-top { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; }.report-subject { flex: 1 1 100%; }.report-reason { margin-right: auto; }.report-row-foot { display: flex; justify-content: flex-end; margin-top: 18px; }.review-layout { grid-template-columns: 1fr; gap: 18px; }.report-review-dialog { width: min(680px, calc(100vw - 32px)); max-height: calc(100dvh - 32px); }.review-footer-hint { display: none; } }
@media(max-width: 480px) { .reports-heading { align-items: flex-start; flex-direction: column; gap: 16px; }.report-queue-heading { padding: 20px; align-items: flex-start; gap: 18px; }.report-status-filter { width: 100%; justify-content: space-between; }.report-pagination { padding: 18px 20px; }.report-review-dialog :deep(> header), .report-review-dialog :deep(> footer) { padding: 14px 18px; }.report-review-dialog :deep(.dialog-body) { padding: 16px 18px; }.review-section, .review-form.account-form { padding: 16px; }.report-row time { flex-basis: 100%; }.report-input-hint { flex-wrap: wrap; }.report-row { padding: 20px; } }
</style>
