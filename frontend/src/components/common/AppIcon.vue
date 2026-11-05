<script setup lang="ts">
defineProps<{ name: string }>()
const paths: Record<string, string> = {
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  lock: 'M5 10h14v11H5V10Zm3 0V6a4 4 0 0 1 8 0v4M12 14v3',
  mail: 'M3 5h18v14H3V5Zm0 0 9 8 9-8',
  flag: 'M5 21V4m0 0c5-4 9 4 14 0v10c-5 4-9-4-14 0',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'm6 6 12 12M6 18 18 6',
  message: 'M4 4h16v12H8l-4 4V4Z M8 8h8M8 12h5',
  bell: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
  refresh: 'M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
  search: 'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  list: 'M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1',
  shield: 'M12 3 3 7v5c0 5 6 8 9 10 3-2 9-5 9-10V7l-9-4Z',
  check: 'm5 12 4 4L19 6',
  compass: 'm16 8-3 5-5 3 3-5 5-3M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  repository: 'M5 3h12l3 3v15H5V3Zm12 0v4h3M8 11h9M8 15h7',
  learn: 'm2 8 10-5 10 5-10 5L2 8Zm4 2v7c4 3 8 3 12 0v-7M22 8v8',
  bookmark: 'M6 3h12v18l-6-4-6 4V3Z',
  clock: 'M12 7v6l4 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  chart: 'M4 20V12h4v8M10 20V8h4v12M16 20V3h4v17',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2',
  settings: 'm9 3-1 3-3 1-2 3 2 2-1 3 3 2 1 3h4l1-3 3-1 2-3-2-2 1-3-3-2-1-3H9Zm6 9a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  logout: 'M9 4H4v16h5M9 12h12m-5-5 5 5-5 5',
  chevron: 'm7 10 5 5 5-5',
  arrow: 'M19 12H5m6-6-6 6 6 6',
}
</script>

<template>
  <svg
    class="app-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  ><path :d="paths[name] || paths.repository" /></svg>
</template>
