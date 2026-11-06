<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { changeFollow, getActivities, getPublicCollection, getPublicProfile, getRelationships } from '../../api/user'
import type { ActivitySummary, PublicProfile, FollowPerson } from '../../api/user'
import type { PublicRoadmap } from '../../types/roadmap'
import { difficultyName, formatDate } from '../../domain/roadmap'
import UserAvatar from '../../components/common/UserAvatar.vue'
import AppIcon from '../../components/common/AppIcon.vue'
import AppDialog from '../../components/common/AppDialog.vue'
import ProfileView from './ProfileView.vue'
import { learningOverview } from '../../api/enrollment'
import { useAuthStore } from '../../stores/auth'
import type { LearningOverview } from '../../types/enrollment'

const auth = useAuthStore(), route = useRoute()
const isPublicProfile = computed(() => route.name !== 'dashboard')
const isListing = computed(() => ['user-published', 'user-collection'].includes(String(route.name)))
const isPeople = computed(() => ['user-following', 'user-followers'].includes(String(route.name)))
const peopleKind = computed(() => route.name === 'user-followers' ? 'followers' as const : 'following' as const)
const people = ref<FollowPerson[]>([]), peoplePage = ref(1), peopleBusy = ref(''), peopleError = ref('')
const profileId = computed(() => String(route.params.userId || auth.user?.id || ''))
const isOwn = computed(() => profileId.value === auth.user?.id)
const homeHref = computed(() => isOwn.value ? '/profile' : '/users/' + profileId.value)
const category = computed(() => route.name === 'user-published' ? 'works' : String(route.params.category))
const page = computed(() => /^\d+$/.test(String(route.query.page || '1')) ? Math.min(1000000, Math.max(1, Number(route.query.page || 1))) : 1)
const listTitle = computed(() => category.value === 'works' ? '发布路线' : category.value === 'favorite' ? '个人收藏' : '个人学习')
const profile = ref<PublicProfile | null>(null)
const works = ref<PublicRoadmap[]>([]), activities = ref<ActivitySummary[]>([])
const total = ref(0), followBusy = ref(false), followError = ref(''), activityError = ref('')
const privacyOpen = ref(false), privacyBusy = ref(false)
const pageSize = computed(() => isListing.value ? 6 : 12)
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const data = ref<LearningOverview | null>(null), month = ref(''), error = ref(''), loading = ref(false)
const activityLabels = { publish: '发布了路线', topic: '发布了话题', checkin: '完成了学习打卡' }
const activityIcons = { publish: 'learn', topic: 'message', checkin: 'check' }
const entries = computed(() => profile.value ? [
  { visible: true, label: '发布路线', count: profile.value.roadmaps.total, icon: 'learn', to: '/users/' + profileId.value + '/routes' },
  { visible: isOwn.value || profile.value.canViewFavorites, label: '个人收藏', count: profile.value.favoriteCount, icon: 'bookmark', to: isOwn.value ? '/favorites' : '/users/' + profileId.value + '/collections/favorite' },
  { visible: isOwn.value || profile.value.canViewLearning, label: '个人学习', count: profile.value.learningCount, icon: 'repository', to: isOwn.value ? '/learning' : '/users/' + profileId.value + '/collections/learning' },
].filter(entry => entry.visible) : [])
const cells = computed(() => {
  if (!data.value) return []
  const [year, number] = data.value.month.split('-').map(Number)
  const offset = new Date(Date.UTC(year!, number! - 1, 1)).getUTCDay()
  const count = new Date(Date.UTC(year!, number!, 0)).getUTCDate()
  return [...Array.from({ length: offset }, () => ''), ...Array.from({ length: count }, (_, i) => data.value!.month + '-' + String(i + 1).padStart(2, '0'))]
})
let generation = 0, loadedIdentity = ''
function activityHref(item: ActivitySummary) {
  return item.issueId ? '/roadmaps/' + item.roadmapId + '/issues/' + item.issueId : '/roadmaps/' + item.roadmapId
}
async function toggleFollow() {
  if (!profile.value?.canFollow || followBusy.value) return
  const ticket = generation, viewer = auth.sessionVersion
  followBusy.value = true; followError.value = ''
  try {
    const result = await changeFollow(profileId.value, !profile.value.isFollowing)
    if (ticket === generation && viewer === auth.sessionVersion && profile.value) Object.assign(profile.value, result)
  } catch (cause) { if (ticket === generation) followError.value = cause instanceof Error ? cause.message : '关注操作失败' }
  finally { if (ticket === generation) followBusy.value = false }
}
async function togglePerson(person: FollowPerson) {
  if (!person.canFollow || peopleBusy.value || loading.value) return
  const ticket = generation, viewer = auth.sessionVersion
  peopleBusy.value = person.id; peopleError.value = ''
  try {
    await changeFollow(person.id, !person.isFollowing)
    if (ticket === generation && viewer === auth.sessionVersion) await load()
  } catch (cause) { if (ticket === generation) peopleError.value = cause instanceof Error ? cause.message : '关注操作失败，请重试' }
  finally { if (ticket === generation) peopleBusy.value = '' }
}
async function load() {
  const ticket = ++generation
  const identity = auth.sessionVersion + ':' + auth.user?.id + ':' + profileId.value
  if (identity !== loadedIdentity || !auth.authenticated) profile.value = null
  loadedIdentity = identity
  people.value = []; peopleBusy.value = ''; peopleError.value = ''
  data.value = null; works.value = []; activities.value = []; total.value = 0
  error.value = ''; activityError.value = ''; loading.value = true; followBusy.value = false; followError.value = ''
  if (!auth.authenticated) { loading.value = false; return }
  try {
    if (!isPublicProfile.value) {
      const result = await learningOverview(month.value || undefined)
      if (ticket === generation) { data.value = result; month.value = result.month }
      return
    }
    if (isPeople.value) {
      const [user, result] = await Promise.all([getPublicProfile(profileId.value, 1, 4), getRelationships(profileId.value, peopleKind.value, page.value)])
      if (ticket !== generation) return
      profile.value = user; people.value = result.items; total.value = result.total; peoplePage.value = result.page
      return
    }
    if (isListing.value) {
      if (!['works', 'favorite', 'learning'].includes(category.value)) throw new Error('列表不存在')
      const user = await getPublicProfile(profileId.value, category.value === 'works' ? page.value : 1, pageSize.value)
      if (ticket !== generation) return
      profile.value = user
      const result = category.value === 'works' ? user.roadmaps : await getPublicCollection(profileId.value, category.value as 'favorite' | 'learning', page.value, pageSize.value)
      if (ticket !== generation) return
      works.value = result.items; total.value = result.total
      return
    }
    const [user, events] = await Promise.allSettled([getPublicProfile(profileId.value, 1, 4), getActivities(profileId.value, 1, 10)])
    if (ticket !== generation) return
    if (user.status === 'rejected') throw user.reason
    profile.value = user.value; works.value = user.value.roadmaps.items.slice(0, 4)
    if (events.status === 'fulfilled') activities.value = events.value.items.slice(0, 10)
    else activityError.value = events.reason instanceof Error ? events.reason.message : '动态加载失败'
  } catch (cause) { if (ticket === generation) error.value = cause instanceof Error ? cause.message : '页面加载失败' }
  finally { if (ticket === generation) loading.value = false }
}
function privacySaved() { privacyOpen.value = false; privacyBusy.value = false; void load() }
watch([() => route.fullPath, () => auth.user?.id, () => auth.sessionVersion], () => { month.value = ''; privacyOpen.value = false; privacyBusy.value = false; void load() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++ })
</script>

<template>
  <section class="content-page">
    <template v-if="isPublicProfile">
      <p
        v-if="loading && !profile"
        role="status"
      >
        正在加载主页…
      </p>
      <p
        v-if="error"
        class="form-error"
        role="alert"
      >
        {{ error }} <button
          type="button"
          class="text-button"
          @click="load"
        >
          重新加载
        </button>
      </p>
      <div
        v-if="profile && !isListing && !isPeople"
        class="public-user-profile"
      >
        <aside
          class="public-user-heading"
          aria-label="作者资料"
        >
          <UserAvatar
            :name="profile.nickname"
            :src="profile.avatarUrl"
          />
          <div class="profile-identity">
            <h1>{{ profile.nickname }}</h1><p>@{{ profile.username }}</p><p
              v-if="profile.bio"
              class="user-bio"
            >
              {{ profile.bio }}
            </p>
          </div>
          <RouterLink
            v-if="isOwn"
            to="/settings"
            class="outline-link edit-profile"
          >编辑个人资料</RouterLink>
          <button
            v-else-if="profile.canFollow"
            type="button"
            class="follow-button"
            :class="{ selected: profile.isFollowing }"
            :aria-pressed="profile.isFollowing"
            :disabled="followBusy"
            @click="toggleFollow"
          >
            {{ followBusy ? '处理中…' : profile.isFollowing ? '已关注' : '关注作者' }}
          </button>
          <p
            v-if="followError"
            class="form-error"
            role="alert"
          >
            {{ followError }}
          </p>
          <p class="follow-counts">
            <RouterLink :to="'/users/' + profileId + '/followers'"><strong>{{ profile.followerCount }}</strong> 位关注者</RouterLink> <span>·</span> <RouterLink :to="'/users/' + profileId + '/following'"><strong>{{ profile.followingCount }}</strong> 人关注中</RouterLink>
          </p>
          <nav
            class="profile-public-counts"
            aria-label="个人内容列表"
          >
            <RouterLink
              v-for="entry in entries"
              :key="entry.label"
              :to="entry.to"
            ><AppIcon :name="entry.icon" /><span>{{ entry.label }}</span><strong>{{ entry.count }}</strong><AppIcon
              name="chevron"
              class="row-chevron"
            /></RouterLink>
          </nav>
          <button
            v-if="isOwn"
            type="button"
            class="privacy-entry"
            @click="privacyOpen = true"
          >
            <AppIcon name="settings" />隐私设置
          </button>
        </aside>
        <div class="profile-content-column">
          <section
            class="profile-works-panel"
            aria-labelledby="profile-works-title"
          >
            <header class="profile-section-heading">
              <div>
                <h2 id="profile-works-title">
                  路线作品
                </h2><p>最近发布的 {{ works.length }} 条路线</p>
              </div>
            </header>
            <p
              v-if="!works.length && !loading"
              class="user-empty"
            >
              暂无公开作品
            </p>
            <div class="profile-route-grid">
              <RouterLink
                v-for="item in works"
                :key="item.id"
                class="profile-route-card"
                :to="'/roadmaps/' + item.id"
              >
                <div class="profile-card-copy"><span class="profile-card-icon"><AppIcon name="repository" /></span><div><h3>{{ item.title }}</h3><p>{{ item.description || '作者尚未填写路线简介' }}</p></div></div>
                <footer><span>{{ item.stageCount }} 个阶段 · {{ item.nodeCount }} 个节点</span><span class="profile-difficulty">{{ difficultyName(item.difficulty) }}</span></footer>
              </RouterLink>
            </div>
          </section>
          <section
            class="profile-activity-panel"
            aria-labelledby="profile-activity-title"
            :aria-busy="loading"
          >
            <header class="profile-section-heading">
              <div>
                <h2 id="profile-activity-title">
                  最近动态
                </h2><p>最近 {{ activities.length }} 条</p>
              </div><button
                type="button"
                class="text-button refresh-activity"
                aria-label="刷新动态"
                :disabled="loading"
                @click="load"
              >
                <AppIcon name="refresh" />
              </button>
            </header>
            <p
              v-if="activityError"
              class="form-error activity-error"
              role="alert"
            >
              {{ activityError }} <button
                type="button"
                class="text-button"
                @click="load"
              >
                重试
              </button>
            </p>
            <p
              v-else-if="!activities.length && !loading"
              class="user-empty"
            >
              暂无可见动态
            </p>
            <ol
              v-if="activities.length"
              class="profile-timeline"
            >
              <li
                v-for="item in activities"
                :key="item.id"
                class="activity-row"
              >
                <span
                  class="timeline-mark"
                  aria-hidden="true"
                ><AppIcon :name="activityIcons[item.activityType]" /></span>
                <div>
                  <time :datetime="item.createdAt">{{ item.activityType === 'checkin' ? item.occurredOn : formatDate(item.createdAt) }}</time><p>
                    {{ activityLabels[item.activityType] }} <RouterLink
                      v-if="item.roadmapId"
                      :to="activityHref(item)"
                      class="activity-target"
                    >{{ item.title }}</RouterLink><span v-else>{{ item.routeCount }} 条公开路线</span>
                  </p>
                </div>
              </li>
            </ol>
          </section>
        </div>
      </div>
      <div
        v-else-if="profile && isPeople"
        class="public-user-profile relationship-list-page"
      >
        <aside class="public-user-heading">
          <RouterLink
            :to="homeHref"
            aria-label="查看作者个人主页"
          ><UserAvatar
            :name="profile.nickname"
            :src="profile.avatarUrl"
          /></RouterLink>
          <div class="profile-identity">
            <h1>{{ profile.nickname }}</h1><p>@{{ profile.username }}</p><p
              v-if="profile.bio"
              class="user-bio"
            >
              {{ profile.bio }}
            </p>
          </div>
          <nav
            class="relationship-nav"
            aria-label="关注列表分类"
          >
            <RouterLink
              :to="'/users/' + profileId + '/following'"
              :aria-current="peopleKind === 'following' ? 'page' : undefined"
              :class="{ active: peopleKind === 'following' }"
            >关注中 <strong>{{ profile.followingCount }}</strong></RouterLink>
            <RouterLink
              :to="'/users/' + profileId + '/followers'"
              :aria-current="peopleKind === 'followers' ? 'page' : undefined"
              :class="{ active: peopleKind === 'followers' }"
            >关注者 <strong>{{ profile.followerCount }}</strong></RouterLink>
          </nav>
          <RouterLink
            :to="homeHref"
            class="profile-back"
          ><AppIcon name="arrow" />返回个人主页</RouterLink>
        </aside>
        <section class="profile-works-panel">
          <header class="profile-section-heading">
            <div><h1>{{ profile.nickname }}的{{ peopleKind === 'following' ? '关注' : '关注者' }}</h1><p>共 {{ total }} 位用户</p></div>
          </header>
          <p
            v-if="peopleError"
            class="form-error"
            role="alert"
          >
            {{ peopleError }}
          </p>
          <p
            v-if="!people.length && !loading"
            class="user-empty"
          >
            {{ peopleKind === 'following' ? '暂未关注其他用户' : '暂无关注者' }}
          </p>
          <ul
            class="relationship-list"
            :aria-busy="loading"
          >
            <li
              v-for="person in people"
              :key="person.id"
              class="relationship-row"
            >
              <RouterLink
                :to="'/users/' + person.id"
                :aria-label="'查看' + person.nickname + '的个人主页'"
              ><UserAvatar
                :name="person.nickname"
                :src="person.avatarUrl"
              /></RouterLink>
              <div class="relationship-copy">
                <RouterLink :to="'/users/' + person.id"><strong>{{ person.nickname }}</strong></RouterLink><span>@{{ person.username }}</span><p>{{ person.bio || '这个人还没有填写简介' }}</p>
              </div>
              <button
                v-if="person.canFollow"
                type="button"
                class="follow-button"
                :class="{ selected: person.isFollowing }"
                :aria-pressed="person.isFollowing"
                :disabled="!!peopleBusy || loading"
                @click="togglePerson(person)"
              >
                {{ peopleBusy === person.id ? '处理中…' : person.isFollowing ? '已关注' : '关注' }}
              </button>
              <span
                v-else
                class="field-hint"
              >我自己</span>
            </li>
          </ul>
          <nav
            v-if="total > 12"
            class="public-work-pages"
            aria-label="关系列表分页"
          >
            <RouterLink
              v-if="peoplePage > 1"
              :to="{ query: { page: String(peoplePage - 1) } }"
              class="outline-link"
            >上一页</RouterLink><span>{{ peoplePage }} / {{ pages }}</span><RouterLink
              v-if="peoplePage < pages"
              :to="{ query: { page: String(peoplePage + 1) } }"
              class="outline-link"
            >下一页</RouterLink>
          </nav>
        </section>
      </div>
      <section
        v-else-if="profile && isListing"
        class="profile-list-page"
      >
        <RouterLink
          :to="homeHref"
          class="profile-back"
        ><AppIcon name="arrow" />返回个人主页</RouterLink>
        <header class="profile-section-heading">
          <div><h1>{{ profile.nickname }}的{{ listTitle }}</h1><p>共 {{ total }} 条当前可见路线</p></div>
        </header>
        <p
          v-if="!works.length && !loading"
          class="user-empty"
        >
          暂无可见路线
        </p>
        <div class="profile-route-grid">
          <RouterLink
            v-for="item in works"
            :key="item.id"
            class="profile-route-card"
            :to="'/roadmaps/' + item.id"
          >
            <div class="profile-card-copy"><span class="profile-card-icon"><AppIcon name="repository" /></span><div><h3>{{ item.title }}</h3><p>{{ item.description || '作者尚未填写路线简介' }}</p></div></div>
            <footer><span>{{ item.stageCount }} 个阶段 · {{ item.nodeCount }} 个节点</span><span class="profile-difficulty">{{ difficultyName(item.difficulty) }}</span></footer>
          </RouterLink>
        </div>
        <nav
          v-if="total > 12"
          class="public-work-pages"
          aria-label="个人列表分页"
        >
          <RouterLink
            v-if="page > 1"
            :to="{ query: { page: String(page - 1) } }"
            class="outline-link"
          >上一页</RouterLink><span>{{ page }} / {{ pages }}</span><RouterLink
            v-if="page < pages"
            :to="{ query: { page: String(page + 1) } }"
            class="outline-link"
          >下一页</RouterLink>
        </nav>
      </section>
      <AppDialog
        v-if="privacyOpen && isOwn"
        class="profile-privacy-dialog"
        title="隐私设置"
        :busy="privacyBusy"
        @close="privacyOpen = false"
      >
        <ProfileView
          privacy-only
          @saved="privacySaved"
          @close="privacyOpen = false"
          @busy="privacyBusy = $event"
        />
        <template #footer>
          <button
            type="button"
            class="outline-link"
            :disabled="privacyBusy"
            @click="privacyOpen = false"
          >
            取消
          </button>
          <button
            type="submit"
            form="profile-privacy-form"
            class="primary-button"
            :disabled="privacyBusy"
          >
            {{ privacyBusy ? '正在保存…' : '保存设置' }}
          </button>
        </template>
      </AppDialog>
    </template>
    <template v-else>
      <header class="discovery-heading">
        <div>
          <p class="eyebrow">
            YOUR PRACTICE
          </p><h1>学习概览与打卡日历</h1><p>仅本人可见。同一天学习多条路线，累计天数仍计为一天。</p>
        </div><RouterLink
          to="/learning"
          class="outline-link"
        >我的学习</RouterLink>
      </header>
      <p
        v-if="loading"
        role="status"
      >
        正在加载…
      </p>
      <p
        v-if="error"
        role="alert"
        class="form-error"
      >
        {{ error }} <button
          type="button"
          class="text-button"
          @click="load"
        >
          重新加载
        </button>
      </p>
      <template v-if="data">
        <div class="learning-overview-stats">
          <div><strong>{{ data.learningRoadmapCount }}</strong>学习中路线</div><div><strong>{{ data.completedNodeCount }}</strong>当前会话已完成节点</div><div><strong>{{ data.checkinDayCount }}</strong>累计打卡天数</div><div><strong>{{ data.currentStreak }}</strong>当前连续天数</div><div><strong>{{ data.longestStreak }}</strong>最长连续天数</div>
        </div>
        <section
          class="calendar-panel"
          aria-label="本人打卡日历"
        >
          <form @submit.prevent="load">
            <label for="calendar-month">查看月份</label> <input
              id="calendar-month"
              v-model="month"
              type="month"
              min="0001-01"
              max="9999-12"
              required
            ><button
              type="submit"
              class="outline-link"
            >
              查看日历
            </button>
          </form>
          <p>今日 {{ data.today }} · 按北京时间统计 · ● 表示有效打卡</p>
          <div class="calendar-grid">
            <span
              v-for="day in ['日','一','二','三','四','五','六']"
              :key="day"
            >{{ day }}</span>
            <span
              v-for="(date, i) in cells"
              :key="i"
              :class="{ checked: data.calendarDates.includes(date) }"
              :aria-label="date ? date + (data.calendarDates.includes(date) ? ' 已打卡' : ' 未打卡') : undefined"
            >{{ date ? Number(date.slice(-2)) : '' }}<small v-if="data.calendarDates.includes(date)">●</small></span>
          </div>
        </section>
      </template>
    </template>
  </section>
</template>

<style scoped>
.relationship-nav { display: grid; gap: 6px; width: 100%; }.relationship-nav a { display: flex; justify-content: space-between; padding: 14px; border-radius: 8px; }.relationship-nav a.active { background: var(--green-soft); color: var(--green); }.relationship-list { list-style: none; margin: 0; padding: 0; }.relationship-row { display: flex; align-items: center; gap: 18px; padding: 22px 0; border-top: 1px solid var(--line); }.relationship-row :deep(.user-avatar) { width: 52px; height: 52px; }.relationship-copy { min-width: 0; flex: 1; overflow-wrap: anywhere; }.relationship-copy strong { font-size: 16px; }.relationship-copy span { display: block; font-size: 13px; color: var(--muted); margin-top: 5px; }.relationship-copy p { font-size: 14px; color: var(--muted); line-height: 1.7; margin: 8px 0 0; white-space: pre-wrap; }.relationship-row .follow-button { width: 100px; flex-shrink: 0; }.relationship-list-page h1 { margin: 0 0 10px; font-size: 25px; }.follow-counts a:hover { color: var(--green); text-decoration: underline; }
@media(max-width: 480px) { .relationship-row { gap: 10px; flex-wrap: wrap; }.relationship-row .follow-button { width: 84px; }.relationship-row :deep(.user-avatar) { width: 40px; height: 40px; }.relationship-copy { min-width: 100px; } }

.profile-privacy-dialog { width: min(700px, calc(100vw - 32px)); }
.profile-privacy-dialog[open] { display: flex; flex-direction: column; max-height: calc(100dvh - 32px); }
.profile-privacy-dialog :deep(> header), .profile-privacy-dialog :deep(> footer) { flex-shrink: 0; padding: 16px 24px; }
.profile-privacy-dialog :deep(.dialog-body) { overflow-y: auto; min-height: 0; padding: 16px 24px; }
.public-user-profile { max-width: 1200px; margin: 12px auto 40px; display: grid; grid-template-columns: 280px minmax(0, 1fr); align-items: start; gap: 28px; }
.public-user-heading, .profile-works-panel, .profile-activity-panel { background: var(--paper); border: 1px solid var(--line); border-radius: 14px; }
.public-user-heading { padding: 26px; display: flex; flex-direction: column; align-items: flex-start; gap: 20px; min-width: 0; }
.public-user-heading :deep(.user-avatar) { width: 84px; height: 84px; }
.profile-identity { width: 100%; min-width: 0; }.profile-identity h1 { font-size: 26px; margin: 0 0 8px; overflow-wrap: anywhere; }.profile-identity p { margin: 6px 0; color: var(--muted); font-size: 14px; line-height: 1.8; overflow-wrap: anywhere; }.profile-identity .user-bio { color: var(--ink); white-space: pre-wrap; margin-top: 16px; }
.edit-profile, .follow-button { width: 100%; min-height: 44px; text-align: center; justify-content: center; }
.follow-button { border: 1px solid var(--green); border-radius: 8px; background: var(--green); color: var(--paper); font-weight: 600; cursor: pointer; }.follow-button.selected { color: var(--green); background: var(--green-soft); }.follow-button:disabled { opacity: .6; cursor: wait; }
.follow-counts { font-size: 13px; color: var(--muted); line-height: 1.8; margin: 0; }.follow-counts strong { color: var(--ink); }.follow-counts span { padding: 0 6px; }
.profile-public-counts { border-top: 1px solid var(--line); padding-top: 12px; width: 100%; display: grid; gap: 4px; }.profile-public-counts a { min-height: 48px; display: flex; align-items: center; gap: 12px; font-size: 14px; border-radius: 6px; }.profile-public-counts a:hover { color: var(--green); background: var(--green-soft); }.profile-public-counts .app-icon, .privacy-entry .app-icon { width: 21px; height: 21px; color: var(--green); flex-shrink: 0; }.profile-public-counts strong { margin-left: auto; font-weight: 500; }.profile-public-counts .row-chevron { width: 16px; height: 16px; transform: rotate(-90deg); }
.privacy-entry { border: 0; border-top: 1px solid var(--line); background: transparent; display: flex; align-items: center; gap: 12px; width: 100%; padding: 20px 0 0; min-height: 44px; color: var(--muted); font-size: 14px; cursor: pointer; }
.profile-content-column { min-width: 0; display: grid; gap: 26px; }.profile-works-panel, .profile-activity-panel { padding: 24px; min-width: 0; }.profile-section-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 22px; }.profile-section-heading h2 { font-size: 22px; margin: 0 0 8px; }.profile-section-heading p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.6; }
.profile-route-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }.profile-route-card { min-width: 0; border: 1px solid var(--line); border-radius: 11px; padding: 20px; display: flex; flex-direction: column; justify-content: space-between; min-height: 192px; transition: border-color .18s, background .18s; }.profile-route-card:hover { border-color: var(--green); background: var(--green-soft); }.profile-card-copy { display: flex; gap: 14px; min-width: 0; }.profile-card-icon { display: grid; place-items: center; background: var(--green-soft); color: var(--green); border-radius: 10px; width: 44px; height: 44px; flex-shrink: 0; }.profile-card-icon .app-icon { width: 25px; height: 25px; }.profile-card-copy > div { min-width: 0; }.profile-card-copy h3 { margin: 0 0 10px; font-size: 16px; line-height: 1.6; overflow-wrap: anywhere; }.profile-card-copy p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.8; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }.profile-route-card footer { border-top: 1px solid var(--line); margin-top: 18px; padding-top: 12px; display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 12px; flex-wrap: wrap; }.profile-difficulty { background: var(--green-soft); color: var(--green); border: 1px solid var(--line); padding: 2px 8px; border-radius: 6px; }
.refresh-activity { min-width: 44px; min-height: 44px; display: grid; place-items: center; }.refresh-activity .app-icon { width: 18px; height: 18px; }.profile-timeline { list-style: none; padding: 0 0 0 14px; margin: 0; }.activity-row { position: relative; display: flex; gap: 18px; padding: 0 0 30px 20px; border-left: 1px solid var(--line); }.activity-row::before { content: ''; position: absolute; left: -4px; top: 18px; width: 7px; height: 7px; border-radius: 50%; background: var(--green); }.activity-row:last-child { padding-bottom: 4px; }.timeline-mark { flex-shrink: 0; width: 38px; height: 38px; border: 1px solid var(--line); border-radius: 50%; background: var(--green-soft); display: grid; place-items: center; color: var(--green); margin-top: 2px; }.timeline-mark .app-icon { width: 20px; height: 20px; }.activity-row > div { min-width: 0; padding-top: 2px; }.activity-row time { color: var(--muted); font-size: 12px; line-height: 1.8; }.activity-row p { font-size: 14px; line-height: 1.9; margin: 4px 0 0; overflow-wrap: anywhere; }.activity-target { color: var(--green); font-weight: 500; text-decoration: underline; text-underline-offset: 3px; }.user-empty { text-align: center; color: var(--muted); padding: 28px 12px; font-size: 14px; line-height: 1.8; }
.profile-list-page { max-width: 1100px; margin: auto; }.profile-list-page .profile-section-heading { margin-top: 26px; }.profile-list-page h1 { font-size: 26px; margin: 0 0 12px; }.profile-back { display: inline-flex; gap: 8px; align-items: center; min-height: 44px; color: var(--green); font-size: 14px; }.profile-back .app-icon { width: 18px; height: 18px; }.public-work-pages { display: flex; gap: 20px; justify-content: center; align-items: center; margin-top: 28px; }
.calendar-panel { padding: 24px; border: 1px solid var(--line); border-radius: 16px; margin-top: 24px; background: var(--paper); }.calendar-panel form { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }.calendar-panel p { color: var(--muted); line-height: 1.8; }.calendar-grid { display: grid; grid-template-columns: repeat(7,minmax(0,1fr)); text-align: center; gap: 4px; max-width: 700px; }.calendar-grid span { min-height: 42px; padding: 8px 0; border-radius: 8px; }.calendar-grid .checked { background: var(--green-soft); color: var(--green); font-weight: 600; }.calendar-grid small { display: block; font-size: 8px; }
@media(max-width: 1050px) { .public-user-profile { grid-template-columns: 240px minmax(0, 1fr); gap: 20px; }.public-user-heading { padding: 20px; }.profile-route-card { padding: 15px; }.profile-card-copy { gap: 10px; }.profile-card-icon { width: 34px; height: 34px; }.profile-card-icon .app-icon { width: 21px; height: 21px; } }
@media(max-width: 820px) { .public-user-profile { grid-template-columns: 1fr; }.public-user-heading { gap: 18px; }.public-user-heading :deep(.user-avatar) { width: 64px; height: 64px; }.edit-profile, .follow-button { max-width: 260px; }.profile-works-panel, .profile-activity-panel { padding: 20px; }.profile-route-grid { gap: 12px; }.profile-card-copy { flex-direction: column; }.profile-route-card { min-height: 218px; }.profile-card-copy h3 { font-size: 15px; }.profile-card-copy p { font-size: 13px; }.profile-section-heading h2 { font-size: 20px; }.activity-row { gap: 12px; padding-left: 14px; }.profile-timeline { padding-left: 4px; }.timeline-mark { width: 30px; height: 30px; }.calendar-panel { padding: 14px; } }
@media(max-width: 360px) { .profile-route-grid { grid-template-columns: 1fr; } }
@media(prefers-reduced-motion: reduce) { .profile-route-card { transition: none; } }
</style>
