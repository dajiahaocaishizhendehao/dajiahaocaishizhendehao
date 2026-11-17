<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, setToken } from './api'
import { useAuth } from './auth'
import ToastHost from './components/ToastHost.vue'

const route = useRoute()
const router = useRouter()
const { currentUser, canWrite, canAdmin, loadCurrentUser, clearCurrentUser } = useAuth()
const isPublic = computed(() => route.meta.public === true)

const navGroups = computed(() => [
  { label: '总览', items: [{ to: '/', text: '工作台', icon: '⌂' }] },
  {
    label: '知识产权',
    items: [
      { to: '/assets', text: '全部知识产权', icon: '◇' },
    ],
  },
  {
    label: '档案管理',
    items: [
      { to: '/materials', text: '材料中心', icon: '▤' },
      { to: '/dates', text: '日期台账', icon: '◷' },
    ],
  },
  {
    label: '财务',
    items: [
      { to: '/fees', text: '费用台账', icon: '¥' },
      { to: '/invoices', text: '发票台账', icon: '▣' },
    ],
  },
  {
    label: '配置',
    items: [
      ...(canWrite.value ? [{ to: '/meta', text: '基础资料', icon: '◎' }] : []),
      ...(canAdmin.value ? [{ to: '/users', text: '系统管理', icon: '⚙' }] : []),
    ],
  },
].filter((group) => group.items.length > 0))

function isActive(to: string): boolean {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}

async function logout() {
  try {
    await api.logout()
  } finally {
    setToken(null)
    clearCurrentUser()
    router.push({ name: 'login' })
  }
}

onMounted(() => { void loadCurrentUser() })
</script>

<template>
  <div v-if="isPublic" class="public-shell">
    <RouterView />
  </div>

  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">IP</div>
        <div class="brand-copy">
          <strong>知产云档</strong>
          <span>IP Asset Center</span>
        </div>
      </div>
      <nav>
        <section v-for="group in navGroups" :key="group.label" class="nav-section">
          <span class="nav-label">{{ group.label }}</span>
          <RouterLink
            v-for="item in group.items"
            :key="item.to"
            :to="item.to"
            class="nav-item"
            :class="{ active: isActive(item.to) }"
          >
            <span class="nav-icon">{{ item.icon }}</span>
            <span>{{ item.text }}</span>
          </RouterLink>
        </section>
      </nav>
      <div class="sidebar-footer">
        <small>本地开发环境</small>
        <small>数据仅存本机数据库</small>
      </div>
    </aside>

    <div class="main-area">
      <header class="topbar">
        <div class="breadcrumb">
          <small>知识产权管理系统</small>
          <span>›</span>
          <strong>{{ route.meta.title || '工作台' }}</strong>
        </div>
        <div class="topbar-actions">
          <span v-if="currentUser" class="badge gray">{{ currentUser.display_name }}</span>
          <button class="button ghost small" @click="logout">退出登录</button>
        </div>
      </header>
      <main class="page">
        <RouterView :key="route.fullPath" />
      </main>
    </div>
  </div>

  <ToastHost />
</template>
