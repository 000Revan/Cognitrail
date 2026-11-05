<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { submitReport, type TargetType } from '../../api/moderation'
import { useAuthStore } from '../../stores/auth'
import AppDialog from './AppDialog.vue'
import AppIcon from './AppIcon.vue'
const props = defineProps<{ targetType: TargetType; targetId: string; targetTitle?: string; withTrigger?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore(), code = ref(''), description = ref(''), busy = ref(false), error = ref(''), submitted = ref(false)
const opened = ref(!props.withTrigger), menuOpen = ref(false)
const menuRoot = ref<HTMLElement>(), menuTrigger = ref<HTMLButtonElement>(), menuItem = ref<HTMLButtonElement>()
const menuPanel = ref<HTMLElement>(), menuAbove = ref(false)
const menuShiftX = ref(0)
const identity = 'report-' + useId()
const kind = computed(() => ({ roadmap: '路线', issue: '话题', comment: '回复' })[props.targetType])
const reasons = [
  { code: 'spam', title: '垃圾广告', hint: '无关推广、刷屏或引流' },
  { code: 'copyright', title: '侵权内容', hint: '未经许可使用他人作品' },
  { code: 'abuse', title: '攻击与骚扰', hint: '侮辱、歧视或恶意骚扰' },
  { code: 'unsafe', title: '违规或危险内容', hint: '含违法或可能造成伤害的信息' },
  { code: 'other', title: '其他问题', hint: '不属于以上类型的问题' },
]
let generation = 0
function reset() { code.value = description.value = error.value = ''; submitted.value = busy.value = false }
function close() { if (busy.value) return; opened.value = false; emit('close') }
async function showMenu() { menuOpen.value = true; await nextTick(); menuItem.value?.focus() }
function openReport() { menuOpen.value = false; reset(); menuTrigger.value?.focus(); opened.value = true }
function menuKeys(event: KeyboardEvent) {
  if (event.key === 'Escape' && menuOpen.value) { event.preventDefault(); event.stopPropagation(); menuOpen.value = false; menuTrigger.value?.focus() }
  else if (event.key === 'Tab') menuOpen.value = false
  else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) { event.preventDefault(); void showMenu() }
}
function outside(event: PointerEvent) { if (!menuRoot.value?.contains(event.target as Node)) menuOpen.value = false }
/** 菜单接近视口底部时向上展开；滚动、缩放后重新核对可用空间。 */
function placeMenu() {
  const trigger = menuTrigger.value, panel = menuPanel.value
  if (!menuOpen.value || !trigger || !panel) return
  const bounds = trigger.getBoundingClientRect()
  const panelBounds = panel.getBoundingClientRect()
  const required = panelBounds.height + 8
  menuAbove.value = window.innerHeight - bounds.bottom < required && bounds.top >= required
  const alignedLeft = (menuRoot.value?.getBoundingClientRect().right ?? bounds.right) - panelBounds.width
  const visibleLeft = Math.max(8, Math.min(alignedLeft, window.innerWidth - panelBounds.width - 8))
  menuShiftX.value = visibleLeft - alignedLeft
}
function stopPlacement() {
  window.removeEventListener('resize', placeMenu)
  window.removeEventListener('scroll', placeMenu, true)
}
watch(menuOpen, async visible => {
  stopPlacement()
  if (!visible) return
  await nextTick()
  if (!menuOpen.value) return
  placeMenu()
  window.addEventListener('resize', placeMenu)
  window.addEventListener('scroll', placeMenu, true)
})
watch([() => auth.sessionVersion, () => props.targetId, () => props.targetType], () => { generation++; opened.value = false; menuOpen.value = false; reset(); emit('close') })
onMounted(() => document.addEventListener('pointerdown', outside))
onBeforeUnmount(() => { generation++; stopPlacement(); document.removeEventListener('pointerdown', outside) })
async function submit() {
  if (busy.value) return
  if (!code.value) { error.value = '请选择举报原因'; return }
  const ticket = generation
  busy.value = true; error.value = ''
  try { await submitReport(props.targetType, props.targetId, code.value, description.value.trim()); if (ticket === generation) submitted.value = true }
  catch (cause) { if (ticket === generation) error.value = cause instanceof Error ? cause.message : '举报提交失败，请重试' }
  finally { if (ticket === generation) busy.value = false }
}
</script>
<template>
  <div
    v-if="withTrigger"
    ref="menuRoot"
    class="report-action-menu"
    @keydown="menuKeys"
    @focusout="event => { if (!menuRoot?.contains(event.relatedTarget as Node | null)) menuOpen = false }"
  >
    <button
      ref="menuTrigger"
      type="button"
      class="report-menu-trigger"
      :aria-label="kind + '更多操作'"
      aria-haspopup="menu"
      :aria-expanded="menuOpen"
      :aria-controls="identity + '-menu'"
      @click="menuOpen = !menuOpen"
    >
      <AppIcon name="more" />
    </button>
    <div
      v-if="menuOpen"
      :id="identity + '-menu'"
      ref="menuPanel"
      class="report-menu-panel"
      :class="{ 'opens-up': menuAbove }"
      :style="{ transform: menuShiftX ? `translateX(${menuShiftX}px)` : undefined }"
      role="menu"
      :aria-label="kind + '操作'"
    >
      <button
        ref="menuItem"
        type="button"
        role="menuitem"
        @click="openReport"
      >
        <AppIcon name="flag" /><span>举报{{ kind }}</span>
      </button>
    </div>
  </div>
  <AppDialog
    v-if="opened"
    class="report-dialog"
    :title="submitted ? '举报已提交' : '举报' + kind"
    :busy="busy"
    @close="close"
  >
    <div
      v-if="submitted"
      class="report-success"
      role="status"
    >
      <span class="report-success-mark"><AppIcon name="check" /></span><h3>感谢你帮助维护社区</h3><p>举报已提交，我们会按内容规范处理。</p><RouterLink
        class="report-history-link"
        to="/reports"
        @click="close"
      >查看我的举报</RouterLink>
    </div>
    <form
      v-else
      :id="identity + '-form'"
      class="report-form"
      @submit.prevent="submit"
    >
      <div class="report-target-context">
        <span class="report-context-icon"><AppIcon :name="targetType === 'roadmap' ? 'repository' : 'message'" /></span><div><small>举报对象 · {{ kind }}</small><strong>{{ targetTitle || kind + ' #' + targetId }}</strong></div>
      </div>
      <fieldset
        class="report-reasons"
        :disabled="busy"
      >
        <legend>这个{{ kind }}有什么问题？<span>请选择一项</span></legend><div class="report-reason-grid">
          <label
            v-for="reason in reasons"
            :key="reason.code"
            class="report-reason-option"
            :class="{ selected: code === reason.code }"
          ><input
            v-model="code"
            type="radio"
            :name="identity + '-reason'"
            :value="reason.code"
            :aria-label="reason.title"
            required
          ><span><strong>{{ reason.title }}</strong><small>{{ reason.hint }}</small></span><AppIcon
            v-if="code === reason.code"
            name="check"
          /></label>
        </div>
      </fieldset>
      <div class="report-description-field">
        <label :for="identity + '-description'">补充说明<span>选填</span></label><textarea
          :id="identity + '-description'"
          v-model="description"
          aria-label="补充说明（选填）"
          rows="4"
          maxlength="2000"
          :disabled="busy"
          placeholder="可以补充问题出现的位置或相关依据，帮助我们核实。"
        /><span class="report-character-count">{{ description.length }} / 2000</span>
      </div>
      <p class="report-privacy-note">
        <AppIcon name="shield" />你的举报身份不会对社区公开。
      </p><p
        v-if="error"
        class="form-error"
        role="alert"
      >
        {{ error }}
      </p>
    </form>
    <template #footer>
      <button
        class="outline-link"
        :disabled="busy"
        @click="close"
      >
        {{ submitted ? '完成' : '取消' }}
      </button><button
        v-if="!submitted"
        class="primary-button"
        type="submit"
        :form="identity + '-form'"
        :disabled="busy || !code"
      >
        {{ busy ? '正在提交…' : '提交举报' }}
      </button>
    </template>
  </AppDialog>
</template>

<style scoped>
.report-action-menu{position:relative;display:inline-flex;flex-shrink:0;align-self:flex-start}.report-menu-trigger{display:grid;place-items:center;width:40px;height:40px;padding:0;border:1px solid var(--line);border-radius:9px;color:var(--muted);background:var(--paper);cursor:pointer;transition:background .18s,color .18s}.report-menu-trigger:hover,.report-menu-trigger[aria-expanded=true]{background:var(--green-soft);color:var(--green);border-color:#cdded3}.report-menu-trigger .app-icon{width:20px;height:20px}.report-menu-panel{position:absolute;top:calc(100% + 6px);right:0;z-index:30;min-width:168px;padding:6px;border:1px solid var(--line);border-radius:10px;background:var(--paper);box-shadow:0 8px 28px #1e38241f}.report-menu-panel button{display:flex;align-items:center;gap:10px;width:100%;min-height:44px;padding:10px 12px;border:0;border-radius:6px;background:transparent;font:inherit;font-size:13px;color:var(--muted);cursor:pointer;text-align:left}.report-menu-panel button:hover,.report-menu-panel button:focus-visible{background:#faf0ed;color:#974c42}.report-menu-panel .app-icon{width:17px;height:17px}
.report-dialog{width:min(560px,calc(100vw - 32px));max-height:calc(100dvh - 40px);padding:0;border:1px solid var(--line);border-radius:16px;box-shadow:0 24px 80px #102e2433}.report-dialog[open]{display:flex;flex-direction:column}.report-dialog :deep(>header){padding:22px 26px;flex-shrink:0}.report-dialog :deep(>header h2){font-size:19px;letter-spacing:0}.report-dialog :deep(.dialog-body){padding:22px 26px;overflow-y:auto;min-height:0}.report-dialog :deep(>footer){padding:16px 26px;background:#fafcfb;flex-shrink:0;gap:10px}.report-dialog :deep(>footer button){min-height:42px;padding:0 20px;font-size:13px}.report-dialog :deep(>footer button:disabled){opacity:.5;cursor:default}.report-form{display:grid;gap:22px;min-width:0}.report-target-context{display:flex;align-items:center;gap:12px;padding:14px;background:#f5f8f6;border:1px solid #e6eee8;border-radius:10px;min-width:0}.report-context-icon{display:grid;place-items:center;width:36px;height:38px;flex-shrink:0;border-radius:8px;color:#5b806b;background:#e8f0eb}.report-context-icon svg{width:19px}.report-target-context>div{min-width:0}.report-target-context small{display:block;font-size:11px;color:var(--muted);margin-bottom:5px}.report-target-context strong{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:13px;font-weight:600;line-height:1.6;overflow-wrap:anywhere}.report-reasons{margin:0;padding:0;border:0;min-width:0}.report-reasons legend{display:flex;align-items:center;gap:10px;font-size:14px;font-weight:600;padding:0;margin-bottom:12px}.report-reasons legend>span{font-size:11px;font-weight:400;color:var(--muted)}.report-reason-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.report-reason-option{display:flex;align-items:flex-start;gap:10px;min-height:76px;padding:13px 12px;border:1px solid #e0e7e2;border-radius:9px;background:#fff;cursor:pointer;transition:background .18s,border-color .18s}.report-reason-option:hover{border-color:#9db6a6;background:#fafcfb}.report-reason-option.selected{background:#f0f7f2;border-color:#5b9878}.report-reason-option input{accent-color:var(--green);width:15px;height:15px;margin:2px 0 0;flex-shrink:0}.report-reason-option>span{flex:1;min-width:0}.report-reason-option strong{display:block;font-size:13px;font-weight:500;line-height:1.5}.report-reason-option small{display:block;font-size:11px;color:var(--muted);line-height:1.6;margin-top:3px}.report-reason-option>svg{width:14px;height:14px;color:var(--green);margin-top:2px;flex-shrink:0}.report-reason-option:last-child{grid-column:1/-1;min-height:66px}.report-description-field{position:relative;min-width:0}.report-description-field label{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:500;margin-bottom:10px}.report-description-field label>span{font-size:11px;color:var(--muted);font-weight:400}.report-description-field textarea{display:block;width:100%;min-height:110px;max-height:220px;padding:12px 13px 28px;resize:vertical;border:1px solid #dce5df;border-radius:9px;background:#fff;font:inherit;font-size:13px;line-height:1.8;color:var(--ink);box-sizing:border-box}.report-description-field textarea:focus{outline:2px solid #95bba64d;outline-offset:1px;border-color:#619879}.report-description-field textarea::placeholder{color:#85958b}.report-character-count{position:absolute;right:12px;bottom:9px;color:#7d8e83;font-size:10px;pointer-events:none}.report-privacy-note{display:flex;align-items:center;gap:7px;margin:0;color:var(--muted);font-size:11px;line-height:1.7}.report-privacy-note svg{width:14px;height:14px;flex-shrink:0}.report-form .form-error{margin:0}.report-success{text-align:center;padding:16px 4px 24px}.report-success-mark{display:grid;place-items:center;width:54px;height:54px;margin:0 auto 18px;border-radius:50%;background:var(--green-soft);color:var(--green)}.report-success h3{font-size:17px;margin:0 0 10px}.report-success p{font-size:13px;line-height:1.8;color:var(--muted)}.report-history-link{display:inline-flex;align-items:center;min-height:40px;margin-top:10px;color:var(--green);font-size:13px}
@media(max-width:600px){.report-dialog{width:calc(100vw - 24px);max-height:calc(100dvh - 24px);border-radius:14px}.report-dialog :deep(>header){padding:18px 20px}.report-dialog :deep(.dialog-body){padding:18px 20px}.report-dialog :deep(>footer){padding:14px 20px}.report-reason-grid{grid-template-columns:minmax(0,1fr)}.report-reason-option,.report-reason-option:last-child{min-height:60px;padding:10px 12px}.report-form{gap:18px}.report-menu-trigger{width:44px;height:44px}.report-reasons legend{flex-wrap:wrap}}
@media(prefers-reduced-motion:reduce){.report-menu-trigger,.report-reason-option{transition:none}}
.report-menu-trigger .app-icon{stroke-width:3}
.report-menu-panel.opens-up{top:auto;bottom:calc(100% + 6px)}
</style>
