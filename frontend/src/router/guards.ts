import type { Pinia } from 'pinia'
import type { Router } from 'vue-router'
import { useAuthStore } from '../stores/auth'

/** 新社区分阶段开放；先于登录守卫执行，旧页面不会挂载或发送旧业务请求。 */
export function installCommunityGuards(router: Router) {
  router.beforeEach(to => {
    if (['profile', 'user-published', 'user-collection', 'user-following', 'user-followers'].includes(String(to.name))) return
    if (String(to.name).startsWith('admin-') || to.name === 'reports') return
    if (!['user-profile', 'roadmap-issues', 'roadmap-issue', 'notifications', 'learning', 'learning-content', 'learning-history', 'dashboard', 'community', 'favorites', 'roadmaps', 'roadmap-detail', 'roadmap-editor', 'roadmap-browse', 'overview', 'community-pending', 'login', 'register', 'settings', 'admin-users', 'forbidden'].includes(String(to.name))) {
      return { name: 'community-pending' }
    }
  })
}

export function installAuthGuards(router: Router, pinia: Pinia) {
  router.beforeEach(to => {
    const auth = useAuthStore(pinia)
    if (to.meta.requiresAuth && !auth.authenticated) {
      return { name: 'login' }
    }
    if (to.meta.requiresAdmin && !auth.isAdmin) return { name: 'forbidden' }
    if (auth.isAdmin && !String(to.name).startsWith('admin-') &&
        !['roadmap-editor', 'roadmap-browse', 'forbidden'].includes(String(to.name))) return { name: 'admin-roadmaps' }
    if (to.meta.guestOnly && auth.authenticated) return { name: 'community' }
    document.title = `${typeof to.meta.title === 'string' ? to.meta.title + ' · ' : ''}知途工坊`
  })
}
