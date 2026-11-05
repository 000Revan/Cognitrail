<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { adminAccounts, changePassword, createAccount, editAccount, getPrivacy, resetAccountPassword, setAccountStatus, updatePrivacy } from '../../api/user'
import { getAccessToken } from '../../api/session'
import { ApiError } from '../../api/http'
import type { PrivacySettings, UserPublic } from '../../types/user'
import { formatDate } from '../../domain/roadmap'
import AppDialog from '../../components/common/AppDialog.vue'
import PasswordField from '../../components/common/PasswordField.vue'
import UserAvatar from '../../components/common/UserAvatar.vue'
import AppIcon from '../../components/common/AppIcon.vue'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const props = defineProps<{ privacyOnly?: boolean }>()
const emit = defineEmits<{ saved: []; close: []; busy: [value: boolean] }>()
const router = useRouter()
const route = useRoute()
const settingsSection = computed(() => props.privacyOnly ? 'privacy' : route.query.section === 'password' ? 'password' : route.query.section === 'privacy' && !auth.isAdmin ? 'privacy' : 'profile')
const settingsNavigation = computed(() => [
  { key: 'profile', label: '个人资料', icon: 'user' },
  { key: 'password', label: '修改密码', icon: 'lock' },
  ...(!auth.isAdmin ? [{ key: 'privacy', label: '隐私设置', icon: 'settings' }] : []),
])
const management = computed(() => route.name === 'admin-users')
const accounts = ref<UserPublic[]>([])
const keyword = ref('')
const role = ref('')
const status = ref('')
const page = ref(1)
const total = ref(0)
const accountsLoading = ref(false)
const accountsError = ref('')
const selectedAccount = ref<UserPublic | null>(null)
const statusBusy = ref(false)
const statusError = ref('')
const accountForm = ref<'create' | 'edit' | 'password' | null>(null)
const formTarget = ref<UserPublic | null>(null)
const formUsername = ref('')
const formNickname = ref('')
const formRole = ref<'user' | 'admin'>('user')
const formPassword = ref('')
const formConfirmation = ref('')
const formBusy = ref(false)
const formError = ref('')
const nickname = ref('')
const avatarInput = ref<HTMLInputElement | null>(null)
const avatarBusy = ref(false)
const avatarError = ref('')
const bio = ref('')
const privacy = ref<PrivacySettings | null>(null)
const privacyLoading = ref(false)
watch(privacyLoading, value => emit('busy', value))
const privacyError = ref('')
const privacyOptions = [
  { key: 'publishPublic', label: '发布路线动态', description: '在主页动态中展示你发布的路线和更新。', icon: 'learn' },
  { key: 'topicPublic', label: '发布话题动态', description: '在主页动态中展示你新发布的话题。', icon: 'message' },
  { key: 'checkinPublic', label: '打卡动态', description: '按日期展示允许公开的学习打卡。', icon: 'check' },
  { key: 'favoritePublic', label: '收藏列表', description: '允许其他用户查看你的个人收藏列表。', icon: 'bookmark' },
  { key: 'learningPublic', label: '学习列表', description: '允许其他用户查看你正在学习的路线。', icon: 'repository' },
] as const
const profileLoading = ref(true)
const passwordLoading = ref(false)
const profileError = ref('')
const passwordError = ref('')
const oldPassword = ref('')
const newPassword = ref('')
const confirmation = ref('')
let request = 0
let profileRequest = 0

function notify(message: string) { ElMessage.closeAll(); ElMessage({ message, type: 'success', duration: 3000, showClose: true, placement: 'bottom' }) }
function clearPasswords() { oldPassword.value = newPassword.value = confirmation.value = '' }
function closeAccountForm() {
  accountForm.value = null; formTarget.value = null
  formPassword.value = ''; formConfirmation.value = ''; formError.value = ''
}
function openAccountForm(mode: 'create' | 'edit' | 'password', target: UserPublic | null = null) {
  closeAccountForm()
  formUsername.value = target?.username || ''; formNickname.value = target?.nickname || ''
  formRole.value = target?.role || 'user'; formTarget.value = target; accountForm.value = mode
}
async function loadAccounts() {
  const ticket = ++request
  accountsLoading.value = true; accountsError.value = ''; accounts.value = []
  try {
    const result = await adminAccounts({ keyword: keyword.value.trim(), role: role.value || undefined,
      status: status.value || undefined, page: page.value })
    if (ticket !== request) return
    accounts.value = result.items; total.value = result.total
    if (!result.items.length && page.value > 1) { page.value--; await loadAccounts() }
  } catch (cause) { if (ticket === request) accountsError.value = cause instanceof Error ? cause.message : '账号加载失败' }
  finally { if (ticket === request) accountsLoading.value = false }
}
function searchAccounts() { page.value = 1; void loadAccounts() }
async function saveAccount() {
  if (formBusy.value || !accountForm.value) return
  formError.value = ''
  if (accountForm.value !== 'edit' && formPassword.value !== formConfirmation.value) {
    formError.value = '两次输入的密码不一致'; return
  }
  const ticket = request
  const session = auth.sessionVersion
  const mode = accountForm.value
  const target = formTarget.value
  formBusy.value = true
  try {
    if (mode === 'create') await createAccount({ username: formUsername.value, nickname: formNickname.value.trim() || null, password: formPassword.value, role: formRole.value })
    else if (mode === 'edit' && target) {
      const updated = await editAccount(target, formNickname.value.trim())
      if (ticket === request && updated.id === auth.user?.id) auth.user = updated
    } else if (mode === 'password' && target) await resetAccountPassword(target.id, formPassword.value)
    if (ticket !== request) return
    closeAccountForm()
    notify(mode === 'create' ? '账号已创建，可以使用初始密码登录。' : mode === 'edit' ? '昵称已更新。' : '密码已重置，旧登录凭证已失效；账号状态保持。')
    await loadAccounts()
  } catch (cause) { if (ticket === request) formError.value = cause instanceof Error ? cause.message : '保存失败，请重试' }
  finally { if (session === auth.sessionVersion) formBusy.value = false }
}
async function changeStatus() {
  if (!selectedAccount.value || statusBusy.value) return
  const ticket = request
  const session = auth.sessionVersion
  const target = selectedAccount.value
  statusBusy.value = true; statusError.value = ''
  try {
    await setAccountStatus(target, target.status === 'active' ? 'disabled' : 'active')
    if (ticket !== request) return
    selectedAccount.value = null
    notify(target.status === 'active' ? '账号已禁用，旧登录凭证已失效。' : '账号已启用，用户可重新登录。')
    await loadAccounts()
  } catch (cause) { if (ticket === request) statusError.value = cause instanceof Error ? cause.message : '状态更新失败，请刷新后重试' }
  finally { if (session === auth.sessionVersion) statusBusy.value = false }
}

async function loadSettings() {
  const ticket = ++profileRequest
  const sentToken = getAccessToken()
  profileLoading.value = true; profileError.value = ''
  try {
    const [profile, settings] = await Promise.all([auth.refreshProfile(), auth.isAdmin ? Promise.resolve(null) : getPrivacy()])
    if (ticket !== profileRequest || sentToken !== getAccessToken()) return
    nickname.value = profile.nickname; bio.value = profile.bio || ''
    privacy.value = settings
  } catch (cause) { if (ticket === profileRequest) profileError.value = cause instanceof Error ? cause.message : '资料加载失败' }
  finally { if (ticket === profileRequest) profileLoading.value = false }
}

watch([() => settingsSection.value, () => route.name, () => auth.user?.id, () => auth.user?.role, () => auth.sessionVersion], () => {
  request++; profileRequest++; ElMessage.closeAll()
  accounts.value = []; total.value = 0; selectedAccount.value = null
  closeAccountForm(); clearPasswords()
  nickname.value = bio.value = ''
  avatarBusy.value = false; avatarError.value = ''
  if (avatarInput.value) avatarInput.value.value = ''
  privacy.value = null; privacyError.value = ''; profileError.value = ''; passwordError.value = ''
  profileLoading.value = true
  passwordLoading.value = privacyLoading.value = formBusy.value = statusBusy.value = false
  if (!auth.authenticated) return
  if (management.value && auth.isAdmin) { page.value = 1; void loadAccounts() }
  else if (!management.value) void loadSettings()
}, { immediate: true })

onBeforeUnmount(() => { request++; profileRequest++; closeAccountForm(); clearPasswords(); privacy.value = null })

async function saveProfile() {
  if (profileLoading.value || avatarBusy.value) return
  const ticket = profileRequest
  profileLoading.value = true; profileError.value = ''
  try {
    const profile = await auth.saveProfile({ nickname: nickname.value.trim(), bio: bio.value })
    if (ticket !== profileRequest) return
    nickname.value = profile.nickname; bio.value = profile.bio || ''
    notify('个人资料已保存。')
  } catch (cause) { if (ticket === profileRequest) profileError.value = cause instanceof Error ? cause.message : '保存失败' }
  finally { if (ticket === profileRequest) profileLoading.value = false }
}
async function changeAvatar(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || avatarBusy.value) return
  const ticket = profileRequest
  avatarBusy.value = true; avatarError.value = ''
  try {
    await auth.uploadAvatar(file)
    if (ticket === profileRequest) notify('头像已更新')
  } catch (cause) {
    if (ticket === profileRequest) avatarError.value = cause instanceof Error ? cause.message : '头像上传失败，请重试'
  } finally { if (ticket === profileRequest) avatarBusy.value = false }
}
async function reloadPrivacy() {
  const ticket = profileRequest
  const sentToken = getAccessToken()
  try {
    const result = await getPrivacy()
    if (ticket === profileRequest && sentToken === getAccessToken()) privacy.value = result
  } catch (cause) { if (ticket === profileRequest) privacyError.value = cause instanceof Error ? cause.message : '隐私设置加载失败' }
}
async function savePrivacy() {
  if (!privacy.value || privacyLoading.value) return
  const ticket = profileRequest
  const sentToken = getAccessToken()
  ElMessage.closeAll()
  privacyLoading.value = true; privacyError.value = ''
  try {
    const result = await updatePrivacy({ ...privacy.value })
    if (ticket !== profileRequest || sentToken !== getAccessToken()) return
    privacy.value = result; notify('隐私设置已保存。'); emit('saved')
  } catch (cause) {
    if (ticket !== profileRequest || sentToken !== getAccessToken()) return
    if (cause instanceof ApiError && cause.status === 409) {
      await reloadPrivacy()
      if (ticket === profileRequest) privacyError.value = '设置已被其他页面修改，已重新加载，请检查后再保存。'
    } else privacyError.value = cause instanceof Error ? cause.message : '隐私设置保存失败'
  } finally { if (ticket === profileRequest) privacyLoading.value = false }
}
async function savePassword() {
  if (passwordLoading.value) return
  passwordError.value = ''
  if (newPassword.value !== confirmation.value) { passwordError.value = '两次输入的新密码不一致'; return }
  const ticket = profileRequest
  const sentToken = getAccessToken()
  passwordLoading.value = true
  try {
    const username = auth.user?.username
    await changePassword(oldPassword.value, newPassword.value)
    if (ticket !== profileRequest || sentToken !== getAccessToken()) return
    clearPasswords(); auth.clear('passwordChanged')
    await router.replace({ name: 'login', query: { reason: 'passwordChanged', username } })
  } catch (cause) { if (ticket === profileRequest) passwordError.value = cause instanceof Error ? cause.message : '修改密码失败' }
  finally { if (ticket === profileRequest) passwordLoading.value = false }
}
</script>

<template>
  <section
    v-if="management"
    class="account-admin-page content-page"
  >
    <header class="profile-heading">
      <div>
        <p class="eyebrow">
          管理中心 / 用户与权限
        </p><h1>账号管理</h1><p>创建普通用户或管理员，维护账号资料与访问权限。</p>
      </div>
      <button
        type="button"
        class="primary-button"
        @click="openAccountForm('create')"
      >
        ＋ 创建账号
      </button>
    </header>
    <form
      class="account-admin-filters"
      @submit.prevent="searchAccounts"
    >
      <div>
        <label for="account-keyword">用户名或昵称</label><input
          id="account-keyword"
          v-model="keyword"
          maxlength="200"
          placeholder="搜索账号"
          type="search"
        >
      </div>
      <div>
        <label for="account-role">角色</label><select
          id="account-role"
          v-model="role"
          @change="searchAccounts"
        >
          <option value="">
            全部角色
          </option><option value="user">
            普通用户
          </option><option value="admin">
            管理员
          </option>
        </select>
      </div>
      <div>
        <label for="account-state">状态</label><select
          id="account-state"
          v-model="status"
          @change="searchAccounts"
        >
          <option value="">
            全部状态
          </option><option value="active">
            启用
          </option><option value="disabled">
            禁用
          </option>
        </select>
      </div>
      <button
        type="submit"
        class="primary-button"
        :disabled="accountsLoading"
      >
        搜索
      </button>
    </form>
    <p
      v-if="accountsLoading"
      class="loading-message"
      role="status"
    >
      正在加载账号…
    </p>
    <p
      v-else-if="accountsError"
      class="form-error"
      role="alert"
    >
      {{ accountsError }} <button
        class="text-button"
        type="button"
        @click="loadAccounts"
      >
        重新加载
      </button>
    </p>
    <p
      v-else-if="!accounts.length"
      class="feature-placeholder"
    >
      没有符合条件的账号，试试调整筛选条件。
    </p>
    <div
      v-else
      class="account-admin-table-wrap"
    >
      <table class="account-admin-table">
        <caption class="library-sr-only">
          账号列表
        </caption>
        <thead>
          <tr>
            <th scope="col">
              账号
            </th><th scope="col">
              角色
            </th><th scope="col">
              状态
            </th><th scope="col">
              注册时间
            </th><th scope="col">
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="account in accounts"
            :key="account.id"
          >
            <td><strong>{{ account.nickname || account.username }}</strong><span>@{{ account.username }}</span><small>ID：{{ account.id }}</small></td>
            <td>{{ account.role === 'admin' ? '管理员' : '普通用户' }}</td>
            <td>
              <span
                class="route-badge"
                :class="(account.status === 'active') ? 'published' : 'disabled'"
              >{{ (account.status === 'active') ? '启用' : '禁用' }}</span>
            </td>
            <td>{{ formatDate(account.createdAt) }}</td>
            <td>
              <div class="account-admin-actions">
                <button
                  type="button"
                  class="outline-link"
                  @click="openAccountForm('edit', account)"
                >
                  编辑昵称
                </button>
                <button
                  v-if="account.role !== 'admin'"
                  type="button"
                  class="outline-link"
                  @click="openAccountForm('password', account)"
                >
                  重置密码
                </button>
                <span
                  v-if="account.role === 'admin'"
                  class="field-hint"
                >管理员保护</span><button
                  v-else
                  type="button"
                  class="outline-link"
                  @click="selectedAccount = account; statusError = ''"
                >
                  {{ (account.status === 'active') ? '禁用账号' : '启用账号' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <footer
      v-if="!accountsError && total"
      class="route-pagination"
    >
      <span>共 {{ total }} 个账号</span><button
        type="button"
        class="outline-link"
        :disabled="accountsLoading || page <= 1"
        @click="page--; loadAccounts()"
      >
        上一页
      </button><span>{{ page }} / {{ Math.max(1, Math.ceil(total / 20)) }}</span><button
        type="button"
        class="outline-link"
        :disabled="accountsLoading || page * 20 >= total"
        @click="page++; loadAccounts()"
      >
        下一页
      </button>
    </footer>
    <AppDialog
      v-if="selectedAccount"
      :title="(selectedAccount.status === 'active') ? '禁用账号' : '启用账号'"
      :busy="statusBusy"
      @close="selectedAccount = null"
    >
      <p>账号：{{ selectedAccount.nickname || selectedAccount.username }}（@{{ selectedAccount.username }}）</p>
      <p>{{ (selectedAccount.status === 'active') ? '禁用后用户将无法登录，已有登录凭证也会失效。路线、收藏和学习数据均保留。' : '启用后用户可以重新登录，原有数据仍保留。' }}</p>
      <p
        v-if="statusError"
        class="form-error"
        role="alert"
      >
        {{ statusError }}
      </p>
      <template #footer>
        <button
          type="button"
          class="outline-link"
          :disabled="statusBusy"
          @click="selectedAccount = null"
        >
          取消
        </button><button
          type="button"
          class="primary-button"
          :disabled="statusBusy"
          @click="changeStatus"
        >
          {{ statusBusy ? '处理中…' : '确认' }}
        </button>
      </template>
    </AppDialog>
    <AppDialog
      v-if="accountForm"
      :title="accountForm === 'create' ? '创建账号' : accountForm === 'edit' ? '编辑账号昵称' : '重置用户密码'"
      :busy="formBusy"
      @close="closeAccountForm"
    >
      <form
        id="admin-account-form"
        class="account-form"
        @submit.prevent="saveAccount"
      >
        <fieldset :disabled="formBusy">
          <div class="form-field">
            <label for="managed-username">用户名</label><input
              id="managed-username"
              v-model="formUsername"
              :disabled="accountForm !== 'create'"
              minlength="3"
              maxlength="30"
              pattern="[A-Za-z0-9_]+"
              autocomplete="off"
              required
            ><p class="field-hint">
              3–30位字母、数字或下划线，统一为小写，创建后不可修改。
            </p>
          </div>
          <div
            v-if="accountForm === 'create'"
            class="form-field"
          >
            <label for="managed-role">账号角色</label><select
              id="managed-role"
              v-model="formRole"
            >
              <option value="user">
                普通用户
              </option><option value="admin">
                管理员
              </option>
            </select><p
              v-if="formRole === 'admin'"
              class="route-info"
            >
              管理员可以管理账号及社区内容，请确认授予此权限。
            </p>
          </div>
          <div
            v-if="accountForm !== 'password'"
            class="form-field"
          >
            <label for="managed-nickname">昵称（创建时选填）</label><input
              id="managed-nickname"
              v-model="formNickname"
              :required="accountForm === 'edit'"
              maxlength="50"
              autocomplete="off"
            >
          </div>
          <template v-if="accountForm !== 'edit'">
            <PasswordField
              id="managed-password"
              v-model="formPassword"
              :label="accountForm === 'create' ? '初始密码' : '新密码'"
              autocomplete="new-password"
              hint="6–30位，自动去除空白。"
            />
            <PasswordField
              id="managed-confirmation"
              v-model="formConfirmation"
              label="确认密码"
              autocomplete="new-password"
            />
          </template>
          <p
            v-if="accountForm === 'password'"
            class="route-info"
          >
            确认重置后，用户原密码及已有登录凭证将失效，原有业务数据与启用状态保留。
          </p>
          <p
            v-if="formError"
            class="form-error"
            role="alert"
          >
            {{ formError }}
          </p>
        </fieldset>
      </form>
      <template #footer>
        <button
          type="button"
          class="outline-link"
          :disabled="formBusy"
          @click="closeAccountForm"
        >
          取消
        </button><button
          type="submit"
          form="admin-account-form"
          class="primary-button"
          :disabled="formBusy"
        >
          {{ formBusy ? '正在保存…' : accountForm === 'create' ? '创建账号' : accountForm === 'password' ? '确认重置密码' : '保存昵称' }}
        </button>
      </template>
    </AppDialog>
  </section>
  <div
    v-else
    class="profile-page"
    :class="{ 'privacy-only': props.privacyOnly }"
  >
    <aside
      v-if="!props.privacyOnly"
      class="settings-sidebar"
    >
      <h1>个人设置</h1>
      <div class="settings-identity">
        <UserAvatar
          :name="auth.user?.nickname || '我'"
          :src="auth.user?.avatarUrl"
        /><div><strong>{{ auth.user?.nickname }}</strong><span>@{{ auth.user?.username }}</span></div>
      </div>
      <nav aria-label="个人设置分类">
        <RouterLink
          v-for="item in settingsNavigation"
          :key="item.key"
          :to="{ path: route.path, query: { section: item.key } }"
          :class="{ active: settingsSection === item.key }"
          :aria-current="settingsSection === item.key ? 'page' : undefined"
        ><AppIcon :name="item.icon" />{{ item.label }}<AppIcon
          name="chevron"
          class="settings-chevron"
        /></RouterLink>
      </nav>
      <RouterLink
        :to="auth.isAdmin ? '/admin/roadmaps' : '/profile'"
        class="settings-back"
      ><AppIcon name="arrow" />{{ auth.isAdmin ? '返回管理中心' : '返回个人主页' }}</RouterLink>
    </aside>
    <div
      class="profile-grid"
      :class="{ 'privacy-only-grid': props.privacyOnly }"
    >
      <p
        v-if="profileError && settingsSection !== 'profile'"
        class="form-error"
        role="alert"
      >
        {{ profileError }}
      </p>
      <section
        v-if="!props.privacyOnly && settingsSection === 'profile'"
        class="profile-card"
        aria-labelledby="profile-title"
      >
        <p class="small-label">
          PROFILE
        </p><h2 id="profile-title">
          个人资料
        </h2><p class="card-description">
          昵称会用于社区中的作者展示。
        </p>
        <section
          v-if="settingsSection === 'profile'"
          class="identity-panel"
          aria-label="当前账号"
        >
          <button
            type="button"
            class="avatar-upload-button"
            aria-label="更换头像"
            :disabled="avatarBusy || profileLoading"
            @click="avatarInput?.click()"
          >
            <UserAvatar
              :name="auth.user?.nickname || auth.user?.username || '我'"
              :src="auth.user?.avatarUrl"
            />
          </button>
          <input
            ref="avatarInput"
            type="file"
            class="avatar-file-input"
            accept="image/png,image/jpeg,image/webp"
            aria-label="选择头像文件"
            @change="changeAvatar"
          >
          <div>
            <h2>{{ auth.user?.nickname || auth.user?.username }}</h2><p>@{{ auth.user?.username }}</p><p>{{ avatarBusy ? '正在上传头像…' : '点击头像上传 PNG、JPEG 或 WebP 图片（默认上限 2 MB，选填）' }}</p>
            <p
              v-if="avatarError"
              class="form-error"
              role="alert"
            >
              {{ avatarError }}
            </p>
          </div>
        </section>
        <form
          class="account-form"
          @submit.prevent="saveProfile"
        >
          <fieldset :disabled="profileLoading || avatarBusy">
            <div class="form-field">
              <label for="profile-username">用户名</label><input
                id="profile-username"
                :value="auth.user?.username"
                disabled
              ><p class="field-hint">
                用户名用于登录，暂不支持修改。
              </p>
            </div>
            <div class="form-field">
              <label for="profile-nickname">昵称</label><input
                id="profile-nickname"
                v-model="nickname"
                maxlength="50"
                autocomplete="nickname"
                required
                minlength="1"
                placeholder="填写社区中展示的昵称"
              >
            </div>
            <div class="form-field">
              <label for="profile-bio">个人简介</label>
              <textarea
                id="profile-bio"
                v-model="bio"
                maxlength="500"
                rows="4"
              />
            </div>
            <p
              v-if="profileError"
              class="form-error"
              role="alert"
            >
              {{ profileError }}
            </p>
            <ElButton
              type="primary"
              native-type="submit"
              :loading="profileLoading"
            >
              保存资料
            </ElButton>
          </fieldset>
        </form>
      </section>
      <section
        v-if="!props.privacyOnly && settingsSection === 'password'"
        class="profile-card"
        aria-labelledby="password-title"
      >
        <p class="small-label">
          SECURITY
        </p><h2 id="password-title">
          修改密码
        </h2><p class="card-description">
          修改后，所有设备都需要重新登录。
        </p>
        <form
          class="account-form"
          @submit.prevent="savePassword"
        >
          <fieldset :disabled="passwordLoading">
            <PasswordField
              id="old-password"
              v-model="oldPassword"
              label="原密码"
              autocomplete="current-password"
            />
            <PasswordField
              id="new-password"
              v-model="newPassword"
              label="新密码"
              autocomplete="new-password"
              hint="6–30 位，自动去除空格。"
            />
            <PasswordField
              id="confirm-new-password"
              v-model="confirmation"
              label="确认新密码"
              autocomplete="new-password"
            />
            <p
              v-if="passwordError"
              class="form-error"
              role="alert"
            >
              {{ passwordError }}
            </p>
            <ElButton
              type="primary"
              native-type="submit"
              :loading="passwordLoading"
            >
              修改密码并重新登录
            </ElButton>
          </fieldset>
        </form>
      </section>
      <section
        v-if="!auth.isAdmin && settingsSection === 'privacy'"
        class="profile-card"
        aria-label="隐私公开范围"
      >
        <p
          v-if="!props.privacyOnly"
          class="small-label"
        >
          PRIVACY
        </p>
        <h2
          v-if="!props.privacyOnly"
          id="privacy-title"
        >
          隐私设置
        </h2>
        <p class="card-description">
          选择哪些内容可以对其他用户公开。收藏或学习设为仅自己可见时，其他用户查看你的主页时会隐藏对应入口与数量；路线作品仍按发布状态展示。
        </p>
        <form
          v-if="privacy"
          :id="props.privacyOnly ? 'profile-privacy-form' : undefined"
          class="account-form"
          aria-label="隐私设置"
          @submit.prevent="savePrivacy"
        >
          <fieldset :disabled="privacyLoading">
            <label
              v-for="option in privacyOptions"
              :key="option.key"
              class="privacy-option"
            >
              <span class="privacy-kind-icon"><AppIcon :name="option.icon" /></span>
              <span class="privacy-copy"><strong>{{ option.label }}</strong><small>{{ option.description }}</small></span>
              <span class="privacy-state">{{ privacy[option.key] ? '公开' : '仅自己' }}</span>
              <input
                v-model="privacy[option.key]"
                type="checkbox"
                role="switch"
                :aria-label="option.label"
                :aria-checked="privacy[option.key]"
              >
            </label>
            <p class="privacy-explanation">
              设为私密后，历史内容也会对他人隐藏；重新公开后，仅恢复仍有效的内容。<small>草稿与详细学习进度始终仅自己可见。</small>
            </p>
            <p
              v-if="privacyError"
              class="form-error"
              role="alert"
            >
              {{ privacyError }}
            </p>
            <div
              v-if="!props.privacyOnly"
              class="privacy-form-actions"
            >
              <ElButton
                type="primary"
                native-type="submit"
                :loading="privacyLoading"
              >
                保存隐私设置
              </ElButton>
            </div>
          </fieldset>
        </form>
        <p
          v-else
          class="field-hint"
        >
          正在加载隐私设置。
        </p>
        <button
          v-if="!privacy && !profileLoading"
          type="button"
          class="text-button"
          @click="loadSettings"
        >
          重新加载账号设置
        </button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.profile-page:not(.privacy-only) { max-width: 1184px; margin: 32px auto; padding: 0 24px; display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 28px; align-items: start; }
.settings-sidebar { position: sticky; top: 100px; padding: 24px 20px; border: 1px solid var(--line); border-radius: 14px; background: var(--paper); min-width: 0; }.settings-sidebar h1 { margin: 0 0 26px; font-size: 22px; }.settings-identity { display: flex; align-items: center; gap: 12px; padding-bottom: 24px; border-bottom: 1px solid var(--line); margin-bottom: 18px; }.settings-identity :deep(.user-avatar) { width: 44px; height: 44px; flex-shrink: 0; }.settings-identity > div { min-width: 0; overflow-wrap: anywhere; }.settings-identity span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); font-size: 12px; margin-top: 6px; }.settings-sidebar nav { display: grid; gap: 8px; }.settings-sidebar nav a { display: flex; gap: 12px; align-items: center; min-height: 50px; padding: 12px; border-radius: 8px; font-size: 14px; }.settings-sidebar nav a.active { background: var(--green-soft); color: var(--green); font-weight: 600; }.settings-sidebar .app-icon { width: 20px; height: 20px; }.settings-chevron { margin-left: auto; transform: rotate(-90deg); }.settings-back { display: flex; gap: 10px; align-items: center; color: var(--muted); font-size: 13px; min-height: 44px; border-top: 1px solid var(--line); margin-top: 22px; padding-top: 16px; }
.profile-grid { display: block; min-width: 0; }.profile-card { padding: 32px; }.profile-card h2 { font-size: 25px; }.profile-card .account-form { max-width: 620px; }.profile-card .identity-panel { margin: 26px 0; padding: 20px; gap: 18px; border-radius: 10px; }.profile-card .identity-panel h2 { display: none; }.profile-card .identity-panel p { font-size: 13px; }.profile-card .identity-panel :deep(.user-avatar) { width: 64px; height: 64px; }.profile-card .small-label { color: var(--green); }.privacy-form-actions { justify-content: flex-start; }
@media(max-width: 760px) { .profile-page:not(.privacy-only) { grid-template-columns: 1fr; padding: 0 16px; margin: 20px auto; gap: 18px; }.settings-sidebar { position: static; padding: 20px; }.settings-sidebar h1 { margin-bottom: 16px; }.settings-sidebar nav { grid-template-columns: 1fr; }.settings-identity { padding-bottom: 16px; margin-bottom: 12px; }.profile-card { padding: 22px; }.profile-card .identity-panel { flex-wrap: wrap; }.settings-back { margin-top: 12px; } }

.privacy-only.profile-page { padding: 0; max-width: none; margin: 0; }
.privacy-only-grid { display: block; }.privacy-only .profile-card { padding: 0; border: 0; box-shadow: none; background: transparent; }.privacy-only .card-description { margin-top: 0; }.privacy-only .account-form { margin-top: 12px; }
.privacy-option { display: flex; align-items: center; gap: 14px; padding: 18px 0; margin: 0; border-bottom: 1px solid var(--line); cursor: pointer; }.privacy-kind-icon { width: 40px; height: 40px; display: grid; place-items: center; color: var(--green); background: var(--green-soft); border-radius: 9px; flex-shrink: 0; }.privacy-kind-icon .app-icon { width: 23px; height: 23px; }.privacy-copy { flex: 1; min-width: 0; }.privacy-copy strong { display: block; font-size: 15px; line-height: 1.8; font-weight: 600; }.privacy-copy small { display: block; font-size: 13px; line-height: 1.8; color: var(--muted); }.privacy-state { color: var(--muted); font-size: 13px; white-space: nowrap; }
.privacy-option input { appearance: none; width: 42px; height: 24px; border: 1px solid var(--line); background: var(--line); border-radius: 20px; position: relative; cursor: pointer; flex-shrink: 0; margin: 0; }.privacy-option input::after { content: ''; position: absolute; height: 18px; width: 18px; left: 2px; top: 2px; background: white; border-radius: 50%; transition: transform .18s; }.privacy-option input:checked { background: var(--green); border-color: var(--green); }.privacy-option input:checked::after { transform: translateX(18px); }.privacy-option input:focus-visible { outline: 2px solid var(--green); outline-offset: 4px; }
.privacy-explanation { font-size: 13px; line-height: 1.9; padding: 14px; border-radius: 10px; background: var(--green-soft); color: var(--muted); margin: 20px 0; }.privacy-explanation small { display: block; font-size: inherit; }.privacy-form-actions { display: flex; justify-content: flex-start; gap: 12px; }.privacy-form-actions button { min-height: 40px; }
@media(max-width: 760px) { .privacy-option { gap: 10px; flex-wrap: wrap; }.privacy-copy { min-width: calc(100% - 60px); }.privacy-state { margin-left: auto; }.privacy-copy strong { font-size: 16px; }.privacy-kind-icon { width: 36px; height: 36px; } }
@media(prefers-reduced-motion: reduce) { .privacy-option input::after { transition: none; } }
</style>
