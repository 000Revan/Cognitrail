<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/common/AppIcon.vue'
import UserAvatar from '../components/common/UserAvatar.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore(), route = useRoute(), router = useRouter()
const opened = ref(false), drawer = ref<HTMLElement>(), trigger = ref<HTMLButtonElement>()
const account = ref(false), busy = ref(false), error = ref('')
const accountRoot = ref<HTMLElement>(), accountTrigger = ref<HTMLButtonElement>()
const links = [
  { to: '/admin/roadmaps', title: '社区路线管理', icon: 'repository', note: '内容审核与治理' },
  { to: '/admin/reports', title: '举报处理', icon: 'shield', note: '受理、复核与结案' },
  { to: '/admin/users', title: '账户管理', icon: 'user', note: '账号与访问权限' },
  { to: '/admin/official-roadmaps', title: '官方路线管理', icon: 'learn', note: '平台内容维护' },
  { to: '/admin/system', title: '系统设置', icon: 'settings', note: '运行信息与系统状态' },
]
const current = computed(() => links.find(link => route.path.startsWith(link.to)) || links[0])
const displayName = computed(() => auth.user?.nickname || auth.user?.username || '管理员')
watch(() => route.fullPath, () => { opened.value = false; account.value = false; error.value = '' })
watch(() => auth.authenticated, value => { if (!value) account.value = false })
async function toggleAccount(event: MouseEvent) {
  account.value = !account.value
  if (account.value && event.detail === 0) {
    await nextTick()
    accountRoot.value?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
  }
}
async function accountKeys(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault(); account.value = false; accountTrigger.value?.focus(); return
  }
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  if (!account.value && !['ArrowDown', 'ArrowUp'].includes(event.key)) return
  event.preventDefault()
  if (!account.value) { account.value = true; await nextTick() }
  const items = Array.from(accountRoot.value?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') || [])
  const current = items.indexOf(document.activeElement as HTMLElement)
  const index = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
    : current < 0 ? (event.key === 'ArrowUp' ? items.length - 1 : 0)
    : (current + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length
  items[index]?.focus()
}
function outsideAccount(event: PointerEvent) {
  if (!accountRoot.value?.contains(event.target as Node)) account.value = false
}
function accountFocusOut(event: FocusEvent) {
  if (!accountRoot.value?.contains(event.relatedTarget as Node | null)) account.value = false
}
async function toggle() {
  account.value = false
  opened.value = !opened.value
  if (opened.value) { await nextTick(); drawer.value?.querySelector<HTMLElement>('a')?.focus() }
}
function close() { opened.value = false; trigger.value?.focus() }
function escape(event: KeyboardEvent) {
  if (opened.value && event.key === 'Escape') { event.preventDefault(); close() }
}
onMounted(() => { window.addEventListener('keydown', escape); document.addEventListener('pointerdown', outsideAccount) })
onBeforeUnmount(() => { window.removeEventListener('keydown', escape); document.removeEventListener('pointerdown', outsideAccount) })
function keys(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); close() }
  if (event.key !== 'Tab') return
  const items = Array.from(drawer.value?.querySelectorAll<HTMLElement>('a, button') || [])
  const first = items[0], last = items.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
async function logout() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await auth.logout(); if (!auth.authenticated) await router.replace('/login') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '退出失败，请重试' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="admin-shell">
    <a
      class="skip-link"
      href="#admin-content"
    >跳转到主要内容</a>
    <header class="admin-topbar">
      <div class="admin-brand-group">
        <button
          ref="trigger"
          class="admin-icon-button"
          type="button"
          aria-label="展开管理侧栏"
          :aria-expanded="opened"
          aria-controls="admin-drawer"
          @click="toggle"
        >
          <AppIcon name="menu" />
        </button>
        <RouterLink
          to="/admin/roadmaps"
          class="admin-brand"
        ><img
          src="/brand-mark.png"
          alt=""
          width="40"
          height="40"
        ><strong>知途工坊</strong><span>管理控制台</span></RouterLink>
      </div>
      <div class="admin-topbar-right">
        <RouterLink
          to="/admin/system"
          class="admin-system-link"
        ><span class="admin-status-dot" />系统信息</RouterLink>
        <span class="admin-topbar-divider" />
        <div
          ref="accountRoot"
          class="account-dropdown admin-account-dropdown"
          @keydown="accountKeys"
          @focusout="accountFocusOut"
        >
          <button
            ref="accountTrigger"
            type="button"
            class="admin-account"
            aria-label="管理员账号菜单"
            aria-haspopup="menu"
            aria-controls="admin-account-menu"
            :aria-expanded="account"
            @click="toggleAccount"
          >
            <UserAvatar :name="displayName" :src="auth.user?.avatarUrl" />
            <span><strong>{{ displayName }}</strong><small>管理员</small></span>
            <AppIcon name="chevron" />
          </button>
          <div v-if="account" id="admin-account-menu" class="account-menu" role="menu" aria-label="管理员账号菜单">
            <RouterLink to="/admin/account" role="menuitem" tabindex="-1" @click="account = false">
              <AppIcon name="settings" /><span>账号设置</span>
            </RouterLink>
            <div class="menu-divider" role="separator" />
            <button type="button" class="logout-button" role="menuitem" tabindex="-1" :disabled="busy" @click="logout">
              <AppIcon name="logout" />{{ busy ? '正在退出…' : '退出登录' }}
            </button>
            <p v-if="error" class="form-error menu-error" role="alert">{{ error }}</p>
          </div>
        </div>
      </div>
    </header>
    <aside
      class="admin-rail"
      aria-label="管理快捷导航"
    >
      <RouterLink
        v-for="link in links"
        :key="link.to"
        :to="link.to"
        :title="link.title"
        :aria-label="link.title"
        :class="{ active: current?.to === link.to }"
        :aria-current="current?.to === link.to ? 'page' : undefined"
      ><AppIcon :name="link.icon" /></RouterLink>
      <span class="admin-rail-bottom"><AppIcon name="shield" /></span>
    </aside>
    <main
      id="admin-content"
      class="admin-content"
      tabindex="-1"
      :inert="opened || undefined"
    >
      <slot />
    </main>
    <template v-if="opened">
      <div
        class="admin-drawer-scrim"
        @click="close"
      />
      <section
        id="admin-drawer"
        ref="drawer"
        class="admin-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="管理导航"
        @keydown="keys"
      >
        <div class="admin-drawer-heading">
          <span>工作空间</span><button
            class="admin-icon-button"
            aria-label="收起管理侧栏"
            @click="close"
          >
            <AppIcon name="close" />
          </button>
        </div>
        <nav aria-label="管理员功能">
          <RouterLink
            v-for="link in links"
            :key="link.to"
            :to="link.to"
            :class="{ active: current?.to === link.to }"
          ><AppIcon :name="link.icon" /><span><strong>{{ link.title }}</strong><small>{{ link.note }}</small></span></RouterLink>
        </nav>
        <div class="admin-drawer-foot">
          <AppIcon name="shield" /><p>管理与维护<br><small>每一次治理，都有迹可循。</small></p>
        </div>
      </section>
    </template>

  </div>
</template>

<style>
.admin-shell{--admin-bg:#f5f7f6;--admin-line:#e3e9e6;--admin-ink:#253c34;--admin-muted:#687c73;--admin-accent:#21694f;min-height:100vh;background:var(--admin-bg);color:var(--admin-ink)}
.admin-topbar{height:76px;position:fixed;z-index:40;inset:0 0 auto;display:flex;justify-content:space-between;align-items:center;padding:0 28px 0 16px;background:#fff;border-bottom:1px solid var(--admin-line);gap:16px}
.admin-brand-group,.admin-brand,.admin-topbar-right,.admin-account{display:flex;align-items:center;gap:16px}.admin-brand{gap:10px}.admin-brand strong{font-size:20px;letter-spacing:1px}.admin-brand>span{border-left:1px solid var(--admin-line);padding-left:16px;font-size:12px;color:var(--admin-muted);margin-left:10px}
.admin-icon-button{display:grid;place-items:center;width:44px;height:44px;border:0;border-radius:10px;background:transparent;color:var(--admin-muted);cursor:pointer}.admin-icon-button:hover{background:#edf4f0;color:var(--admin-accent)}
.admin-system-link{display:flex;align-items:center;gap:8px;font-size:13px}.admin-status-dot{width:7px;height:7px;border-radius:50%;background:#668477}.admin-topbar-divider{height:28px;width:1px;background:var(--admin-line)}.admin-account{border:0;background:transparent;cursor:pointer;text-align:left;gap:10px}.admin-account strong,.admin-account small{display:block}.admin-account strong{font-size:13px}.admin-account small{font-size:11px;color:var(--admin-muted);margin-top:4px}.admin-account>.app-icon{width:16px}
.admin-rail{position:fixed;z-index:30;left:0;top:76px;bottom:0;width:76px;background:#fff;border-right:1px solid var(--admin-line);display:flex;flex-direction:column;align-items:center;gap:12px;padding:24px 0}.admin-rail>a{display:grid;place-items:center;width:46px;height:46px;color:#7c8d85;border-radius:12px;transition:background .18s,color .18s}.admin-rail>a:hover,.admin-rail>a.active{background:#e8f2ec;color:var(--admin-accent)}.admin-rail-bottom{margin-top:auto;color:#a4b4ab;padding-bottom:12px}
.admin-content{padding:112px 40px 40px;margin-left:76px;min-width:0;outline:none}.admin-content>.content-page{max-width:1400px;margin:auto}.admin-content .content-page{width:100%}
.admin-drawer-scrim{position:fixed;z-index:49;inset:76px 0 0;background:#152d244d}.admin-drawer{position:fixed;z-index:50;left:0;top:76px;bottom:0;width:min(292px,85vw);background:#fff;box-shadow:12px 0 36px #17392b14;display:flex;flex-direction:column;padding:20px 16px;animation:admin-slide .2s ease-out}.admin-drawer-heading{display:flex;align-items:center;justify-content:space-between;padding:0 12px 12px;color:var(--admin-muted);font-size:12px;letter-spacing:1px}.admin-drawer nav{display:grid;gap:8px}.admin-drawer nav a{display:flex;align-items:center;gap:14px;padding:16px;border-radius:12px;color:var(--admin-muted)}.admin-drawer nav a:hover,.admin-drawer nav a.active{background:#eaf3ed;color:var(--admin-accent)}.admin-drawer nav strong,.admin-drawer nav small{display:block}.admin-drawer nav strong{font-size:14px}.admin-drawer nav small{font-size:11px;margin-top:6px;font-weight:400}.admin-drawer-foot{margin-top:auto;padding:20px 14px;display:flex;align-items:center;gap:12px;color:var(--admin-muted)}.admin-drawer-foot p{font-size:13px;line-height:1.8}.admin-drawer-foot small{font-size:11px}
@keyframes admin-slide{from{transform:translateX(-100%)}to{transform:translateX(0)}}
.admin-page{max-width:1400px;margin:0 auto}.admin-page-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:28px}.admin-page-heading h1{font-size:28px;letter-spacing:-.5px;margin:6px 0 10px;font-weight:650}.admin-eyebrow{color:#789286;font-size:10px;letter-spacing:2px;font-weight:600;margin:0}.admin-page-heading p:not(.admin-eyebrow){font-size:13px;color:var(--admin-muted);margin:0;line-height:1.8}.admin-panel{border:1px solid var(--admin-line);border-radius:16px;background:#fff;overflow:hidden;box-shadow:0 4px 24px #294b381f}.admin-breadcrumb{display:flex;gap:10px;font-size:12px;color:var(--admin-muted);margin-bottom:24px}.admin-count{font-size:12px;color:var(--admin-muted);white-space:nowrap}.admin-count strong{font-size:24px;color:var(--admin-ink);margin:0 5px}.admin-footer-note{display:flex;align-items:center;gap:8px;color:var(--admin-muted);font-size:12px;margin-top:20px}.admin-footer-note svg{width:16px}
@media(max-width:760px){.admin-topbar{height:68px;padding:0 12px;gap:4px}.admin-brand-group{gap:4px}.admin-brand strong{font-size:16px}.admin-brand img{width:32px;height:32px}.admin-brand>span,.admin-system-link,.admin-topbar-divider,.admin-account>span,.admin-account>.app-icon{display:none}.admin-topbar-right{gap:0}.admin-rail{width:60px;top:68px}.admin-rail>a{width:44px;height:44px}.admin-content{margin-left:60px;padding:92px 14px 24px}.admin-page-heading{align-items:flex-start;margin-bottom:20px;flex-wrap:wrap}.admin-page-heading h1{font-size:24px}.admin-drawer,.admin-drawer-scrim{top:68px}.admin-count strong{font-size:20px}}
@media(prefers-reduced-motion:reduce){.admin-drawer{animation:none}.admin-rail>a{transition:none}}
.admin-account>.user-avatar{display:inline-flex;flex-shrink:0}.admin-account{min-height:44px}.admin-account strong{max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.admin-shell .danger-button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 20px;background:#fff4f2;border:1px solid #e7c1ba;border-radius:8px;color:#a14439;font-size:13px;font-weight:600;cursor:pointer;transition:background .18s}.admin-shell .danger-button:hover{background:#fbe7e3}.admin-shell .danger-button:disabled{opacity:.5;cursor:default}
.admin-rail{overflow-y:auto}.admin-rail>a{flex-shrink:0}
.admin-account-dropdown{position:relative}
.admin-account-dropdown .account-menu{width:210px;max-width:calc(100vw - 24px);top:calc(100% + 12px)}
.admin-account[aria-expanded="true"]>.app-icon{transform:rotate(180deg)}
</style>
