<script setup lang="ts">
import AppIcon from '../components/common/AppIcon.vue'
</script>

<template>
  <main class="auth-shell">
    <div class="auth-page-heading">
      <RouterLink
        class="brand auth-brand"
        to="/"
        aria-label="返回知途工坊"
      >
        <img
          src="/brand-mark.png"
          alt=""
          width="48"
          height="48"
        >
        <span><strong>知途工坊</strong><small>Cognitrail</small></span>
      </RouterLink>
      <RouterLink
        class="auth-back"
        to="/"
      ><AppIcon name="arrow" />返回社区</RouterLink>
    </div>
    <div class="auth-card">
      <section
        class="auth-story"
        aria-label="知途工坊"
      >
        <svg
          class="auth-illustration"
          viewBox="0 0 440 300"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="m15 230 70-70 48 43 47-35 85 62M270 80l55-55 75 55"
            fill="var(--green-soft)"
          />
          <path
            d="M76 62c0 58 220 6 220 76S130 163 130 220s220 12 220 52"
            stroke="#9eb8a9"
            stroke-width="2"
            stroke-dasharray="7 6"
          />
          <g
            fill="var(--paper)"
            stroke="#64927d"
            stroke-width="2"
          >
            <rect
              x="44"
              y="25"
              width="64"
              height="60"
              rx="8"
            />
            <rect
              x="266"
              y="104"
              width="64"
              height="60"
              rx="8"
            />
            <rect
              x="98"
              y="202"
              width="64"
              height="60"
              rx="8"
            />
            <rect
              x="318"
              y="230"
              width="64"
              height="54"
              rx="8"
            />
          </g>
          <g
            stroke="#64927d"
            stroke-width="2"
            stroke-linecap="round"
          >
            <path d="M60 43h32M60 54h24M60 65h17M332 246h32M332 257h24M332 268h15M119 221l-8 9 8 9M141 221l8 9-8 9M134 218l-8 24" />
            <path
              d="M282 148v-12M298 148v-24M314 148v-32"
              stroke-width="6"
            />
          </g>
          <g fill="var(--green)"><circle
            cx="166"
            cy="96"
            r="5"
          /><circle
            cx="236"
            cy="180"
            r="5"
          /><circle
            cx="238"
            cy="253"
            r="5"
          /></g>
        </svg>
        <p class="eyebrow">
          A PATH WORTH SHARING
        </p>
        <h1>把经验连成路线</h1>
        <p>跟随他人的经验，找到自己的学习路径。<br>也把你的探索，分享给后来的人。</p>
      </section>
      <section
        class="auth-main"
        aria-label="账号表单"
      >
        <div class="auth-content">
          <slot />
        </div>
      </section>
    </div>
    <p class="auth-footnote">
      知途工坊 · Cognitrail
    </p>
  </main>
</template>
