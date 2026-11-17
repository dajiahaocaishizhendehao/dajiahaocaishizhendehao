import { createRouter, createWebHashHistory } from 'vue-router'
import { getToken } from './api'
import { ensureAuthLoaded } from './auth'

import LoginView from './views/LoginView.vue'
import DashboardView from './views/DashboardView.vue'
import AssetsView from './views/AssetsView.vue'
import AssetDetailView from './views/AssetDetailView.vue'
import InvoicesView from './views/InvoicesView.vue'
import MaterialsView from './views/MaterialsView.vue'
import DatesView from './views/DatesView.vue'
import FeesView from './views/FeesView.vue'
import FeeDetailView from './views/FeeDetailView.vue'
import UsersView from './views/UsersView.vue'
import MetaView from './views/MetaView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true, title: '登录' } },
    { path: '/', name: 'dashboard', component: DashboardView, meta: { title: '工作台' } },
    { path: '/assets', name: 'assets', component: AssetsView, meta: { title: '全部知识产权' } },
    { path: '/assets/:id', name: 'asset-detail', component: AssetDetailView, meta: { title: '档案详情' } },
    { path: '/trademarks', redirect: '/assets' },
    { path: '/invoices', name: 'invoices', component: InvoicesView, meta: { title: '发票台账' } },
    { path: '/materials', name: 'materials', component: MaterialsView, meta: { title: '材料中心' } },
    { path: '/dates', name: 'dates', component: DatesView, meta: { title: '日期台账' } },
    { path: '/fees', name: 'fees', component: FeesView, meta: { title: '费用台账' } },
    { path: '/fees/:id', name: 'fee-detail', component: FeeDetailView, meta: { title: '费用详情' } },
    { path: '/users', name: 'users', component: UsersView, meta: { title: '系统管理', permission: 'admin' } },
    { path: '/meta', name: 'meta', component: MetaView, meta: { title: '基础资料', permission: 'write' } },
    // 已下线的旧页面回落到工作台，避免旧链接白屏
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  if (!getToken()) return { name: 'login' }

  const user = await ensureAuthLoaded()
  if (!user) return { name: 'login' }
  if (to.meta.permission === 'admin' && user.role !== 'admin') return { name: 'dashboard' }
  if (to.meta.permission === 'write' && !['admin', 'ip_admin'].includes(user.role)) return { name: 'dashboard' }
  return true
})

router.afterEach((to) => {
  const title = (to.meta.title as string) || '知识产权管理系统'
  document.title = `${title} · 知产云档`
})
