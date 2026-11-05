<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/common/AppIcon.vue'
import UserAvatar from '../components/common/UserAvatar.vue'
import AdminLayout from './AdminLayout.vue'
import { useAuthStore } from '../stores/auth'
import { unreadCount } from '../api/notification'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const accountOpen = ref(false)
const accountRoot = ref<HTMLElement>()
const avatarButton = ref<HTMLButtonElement>()
const loggingOut = ref(false)
const logoutError = ref('')
const displayName = computed(() => auth.user?.nickname || auth.user?.username || '')
const messageCount = ref(0)
let messageRequest = 0
let messagePolling: ReturnType<typeof setInterval> | undefined
/** 只在登录会话内轮询；旧账号结果不写回当前导航。 */
async function refreshMessages() {
  const ticket = ++messageRequest, viewer = auth.sessionVersion
  if (!auth.authenticated || auth.isAdmin) { messageCount.value = 0; return }
  try { const count = await unreadCount(); if (ticket === messageRequest && viewer === auth.sessionVersion) messageCount.value = count } catch { /* 网络恢复后下一次轮询重试，消息页显示具体错误。 */ }
}
watch([() => auth.sessionVersion, () => auth.user?.id, () => route.fullPath], () => { messageCount.value = 0; void refreshMessages() }, { immediate: true })
const accountLinks = computed(() => auth.isAdmin ? [
  { to: '/admin/users', label: '账号管理', icon: 'user' },
  { to: '/settings', label: '账号设置', icon: 'settings' },
] : [
  { to: '/profile', label: '个人主页', icon: 'user' },
  { to: '/settings', label: '账号设置', icon: 'settings' },
  { to: '/reports', label: '我的举报', icon: 'shield' },
])
/** 顶部导航按业务区域高亮，公开详情与作者工作稿分别归属。 */
function sectionCurrent(section: 'community' | 'favorites' | 'creation') {
  if (section === 'favorites') return route.name === 'favorites'
  const creation = ['roadmaps', 'roadmap-editor', 'roadmap-browse'].includes(String(route.name)) ||
    route.name === 'roadmap-detail' && route.query.preview === 'draft'
  return section === 'creation' ? creation : route.name === 'community' || route.name === 'roadmap-detail' && !creation
}

/** 导航切换后关闭覆盖层，避免新页面仍被遮挡。 */
watch(() => route.fullPath, () => { accountOpen.value = false; logoutError.value = '' })
watch(() => auth.authenticated, value => { if (!value) accountOpen.value = false })

async function toggleAccount(event: MouseEvent) {
  accountOpen.value = !accountOpen.value
  // 鼠标打开时保留头像焦点；键盘打开才定位首项，避免产生默认选中的观感。
  if (accountOpen.value && event.detail === 0) {
    await nextTick()
    accountRoot.value?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
  }
}

async function accountKeys(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    accountOpen.value = false
    avatarButton.value?.focus()
    return
  }
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  if (!accountOpen.value && !['ArrowDown', 'ArrowUp'].includes(event.key)) return
  event.preventDefault()
  if (!accountOpen.value) {
    accountOpen.value = true
      await nextTick()
  }
  const items = Array.from(accountRoot.value?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') || [])
  const current = items.indexOf(document.activeElement as HTMLElement)
  const index = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
    : current < 0 ? (event.key === 'ArrowUp' ? items.length - 1 : 0)
    : (current + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length
  items[index]?.focus()
}

function outsideAccount(event: PointerEvent) {
  if (!accountRoot.value?.contains(event.target as Node)) accountOpen.value = false
}

function accountFocusOut(event: FocusEvent) {
  if (!accountRoot.value?.contains(event.relatedTarget as Node | null)) accountOpen.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', outsideAccount)
  window.addEventListener('cognitrail:notifications-changed', refreshMessages)
  messagePolling = setInterval(() => void refreshMessages(), 15000)
})
onBeforeUnmount(() => {
  messageRequest++
  if (messagePolling) clearInterval(messagePolling)
  document.removeEventListener('pointerdown', outsideAccount)
  window.removeEventListener('cognitrail:notifications-changed', refreshMessages)
})

async function logout() {
  if (loggingOut.value) return
  loggingOut.value = true
  logoutError.value = ''
  try {
    await auth.logout()
    if (!auth.authenticated) await router.replace({ name: 'login' })
  } catch (cause) {
    logoutError.value = cause instanceof Error ? cause.message : '退出失败，请稍后重试'
  } finally { loggingOut.value = false }
}
</script>

<template>
  <AdminLayout v-if="auth.isAdmin">
    <RouterView />
  </AdminLayout>
  <div
    v-else
    class="app-shell unified-shell"
  >
    <a
      class="skip-link"
      href="#main-content"
    >跳转到主要内容</a>
    <header class="topbar">
      <div class="topbar-brand">
        <RouterLink
          class="brand"
          to="/"
          aria-label="知途工坊首页"
        >
          <img
            src="/brand-mark.png"
            alt=""
            width="48"
            height="48"
          >
          <span><strong>知途工坊</strong><small>Cognitrail</small></span>
        </RouterLink>
      </div>
      <nav
        class="site-navigation"
        aria-label="主导航"
      >
        <RouterLink
          to="/"
          :class="{ 'nav-current': sectionCurrent('community') }"
          :aria-current="sectionCurrent('community') ? 'page' : undefined"
        >社区发现</RouterLink>
        <RouterLink
          to="/favorites"
          :class="{ 'nav-current': sectionCurrent('favorites') }"
          :aria-current="sectionCurrent('favorites') ? 'page' : undefined"
        >我的收藏</RouterLink>
        <RouterLink
          to="/roadmaps"
          :class="{ 'nav-current': sectionCurrent('creation') }"
          :aria-current="sectionCurrent('creation') ? 'page' : undefined"
        >我的创作</RouterLink>
        <RouterLink
          to="/learning"
          :class="{ 'nav-current': String(route.name).startsWith('learning') || route.name === 'dashboard' }"
        >我的学习</RouterLink>
      </nav>
      <div class="account-actions">
        <RouterLink
          v-if="auth.authenticated"
          to="/notifications"
          class="message-link"
          :aria-label="messageCount ? '消息，' + messageCount + ' 条未读' : '消息'"
          title="站内消息"
        ><AppIcon name="mail" /><span
          v-if="messageCount"
          class="message-badge"
          aria-hidden="true"
        >{{ messageCount > 99 ? '99+' : messageCount }}</span></RouterLink>
        <div
          v-if="auth.user"
          ref="accountRoot"
          class="account-dropdown"
          @keydown="accountKeys"
          @focusout="accountFocusOut"
        >
          <button
            ref="avatarButton"
            type="button"
            class="avatar-trigger"
            aria-label="打开账号菜单"
            aria-haspopup="menu"
            :aria-expanded="accountOpen"
            aria-controls="account-menu"
            @click="toggleAccount"
          >
            <UserAvatar
              :name="displayName"
              :src="auth.user.avatarUrl"
            />
            <AppIcon name="chevron" />
          </button>
          <div
            v-if="accountOpen"
            id="account-menu"
            class="account-menu"
            role="menu"
            aria-label="账号菜单"
          >
            <div
              class="account-menu-identity"
              role="presentation"
            >
              <UserAvatar
                :name="displayName"
                :src="auth.user.avatarUrl"
              />
              <div><strong>{{ displayName }}</strong><span>@{{ auth.user.username }}</span></div>
            </div>
            <RouterLink
              v-for="item in accountLinks"
              :key="item.to"
              :to="item.to"
              role="menuitem"
              tabindex="-1"
              @click="accountOpen = false"
            >
              <AppIcon :name="item.icon" /><span>{{ item.label }}</span>
            </RouterLink>
            <div
              class="menu-divider"
              role="separator"
            />
            <button
              type="button"
              class="logout-button"
              role="menuitem"
              tabindex="-1"
              :disabled="loggingOut"
              @click="logout"
            >
              <AppIcon name="logout" />{{ loggingOut ? '正在退出…' : '退出登录' }}
            </button>
            <p
              v-if="logoutError"
              class="form-error menu-error"
              role="alert"
            >
              {{ logoutError }}
            </p>
          </div>
        </div>
        <template v-else>
          <RouterLink to="/login">登录</RouterLink>
          <RouterLink
            class="join-link"
            to="/register"
          >注册</RouterLink>
        </template>
      </div>
    </header>
    <div class="workspace">
      <main
        id="main-content"
        tabindex="-1"
      >
        <RouterView />
      </main>
      <footer class="workspace-footer">
        <span>知途工坊 · Cognitrail</span><RouterLink to="/environment">运行环境</RouterLink><span>让经验成为路径。</span>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.message-link { position: relative; display: inline-flex; align-items: center; justify-content: center; min-width: 44px; min-height: 44px; border-radius: 50%; color: var(--green); }
.message-link:hover { background: var(--green-soft); }.message-link .app-icon { width: 24px; height: 24px; }
.message-badge { position: absolute; top: 1px; right: -2px; min-width: 19px; height: 19px; padding: 0 4px; display: grid; place-items: center; border-radius: 12px; background: var(--green); color: white; font-size: 11px; line-height: 1; border: 2px solid var(--paper); font-variant-numeric: tabular-nums; }
.unified-shell .workspace { margin-left: 0; }
.unified-shell .topbar { padding-left: 32px; }
.site-navigation { display: flex; gap: 32px; height: 100%; align-items: center; font-size: 14px; color: var(--muted); }
.site-navigation a { display: flex; align-items: center; min-height: 44px; height: 100%; border-bottom: 2px solid transparent; }
.site-navigation a:hover { color: var(--green); }
.site-navigation a.nav-current { color: var(--green); border-bottom-color: var(--green); font-weight: 600; }
@media(max-width: 760px) { .unified-shell .topbar { padding: 0 16px; flex-wrap: wrap; height: 120px; gap: 0 12px; } .unified-shell .topbar-brand { height: 66px; } .site-navigation { order: 3; width: 100%; height: 54px; gap: 28px; justify-content: center; } .unified-shell .workspace { padding-top: 120px; } }
</style>
