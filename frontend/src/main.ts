import { createApp, watch } from 'vue'
import { createPinia } from 'pinia'
import { ElButton, ElConfigProvider, ElMessage, ElTag } from 'element-plus'
import 'element-plus/es/components/base/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/tag/style/css'
import 'element-plus/es/components/message/style/css'
import './styles/index.css'
import App from './App.vue'
import { router } from './router'
import { installAuthGuards, installCommunityGuards } from './router/guards'
import { useAuthStore } from './stores/auth'
import './styles/account.css'
import './styles/roadmap.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
installCommunityGuards(router)
installAuthGuards(router, pinia)
const auth = useAuthStore(pinia)
watch([() => router.currentRoute.value.fullPath, () => auth.sessionVersion, () => auth.user?.id], () => ElMessage.closeAll())
watch(() => auth.authenticated, (authenticated, previous) => {
  if (!authenticated && previous && auth.endReason === 'expired' && router.currentRoute.value.meta.requiresAuth) {
    void router.replace({ name: 'login', query: { reason: 'expired' } })
  }
})
app.use(router)
app.component('ElButton', ElButton).component('ElTag', ElTag).component('ElConfigProvider', ElConfigProvider)
app.mount('#app')
