<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, formatDate, statusLabels, typeLabels, type AssetListItem } from '../api'
import { useAuth } from '../auth'
import { useToast } from '../toast'
import AssetFormDrawer from '../components/AssetFormDrawer.vue'

const route = useRoute()
const { canWrite } = useAuth()
const toast = useToast()

const items = ref<AssetListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const error = ref('')

const filters = reactive({ q: '', ip_type: '', status_group: '' })

const showDrawer = ref(false)
const editingId = ref<string | null>(null)
const deleteTarget = ref<AssetListItem | null>(null)
const deleting = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | undefined

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await api.assets({ ...filters, page: page.value, page_size: pageSize })
    items.value = result.items
    total.value = result.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  showDrawer.value = true
}

function openEdit(id: string) {
  editingId.value = id
  showDrawer.value = true
}

function onSaved() {
  showDrawer.value = false
  void load()
}

function scheduleSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; void load() }, 250)
}

async function exportAssets(kind: 'csv' | 'xlsx') {
  try {
    if (kind === 'csv') await api.exportAssetsCsv(filters)
    else await api.exportAssetsXlsx(filters)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '导出失败')
  }
}

function openDelete(item: AssetListItem) {
  deleteTarget.value = item
}

function closeDelete() {
  if (deleting.value) return
  deleteTarget.value = null
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await api.deleteAsset(deleteTarget.value.id)
    toast.success('档案已删除')
    deleteTarget.value = null
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败'
    deleteTarget.value = null
  } finally {
    deleting.value = false
  }
}

function reset() {
  filters.q = ''
  filters.ip_type = ''
  filters.status_group = ''
  page.value = 1
  void load()
}

onMounted(async () => {
  await load()
  if (!canWrite.value) return
  if (route.query.create === '1') openCreate()
  else if (route.query.edit) openEdit(String(route.query.edit))
})
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h1>全部知识产权</h1>
        <p>统一查询专利、软件著作权与商标档案</p>
      </div>
    </div>

    <div class="toolbar">
      <button v-if="canWrite" class="button primary" @click="openCreate">＋ 新建档案</button>
      <input v-model="filters.q" class="field" placeholder="搜索案件名称或我方文号" @input="scheduleSearch" @keyup.enter="page = 1; load()" />
      <select v-model="filters.ip_type" class="field" @change="page = 1; load()">
        <option value="">全部类型</option>
        <option value="patent">专利</option>
        <option value="copyright">软件著作权</option>
        <option value="trademark">商标 / Logo</option>
      </select>
      <select v-model="filters.status_group" class="field" @change="page = 1; load()">
        <option value="">全部状态</option>
        <option value="in_progress">办理中</option>
        <option value="granted">已取得权利</option>
        <option value="invalid">已失效</option>
        <option value="other">其他</option>
      </select>
      <button class="button small" @click="page = 1; load()">查询</button>
      <button class="button ghost small" @click="reset">重置</button>
      <button class="button ghost small" @click="exportAssets('csv')">导出 CSV</button>
      <button class="button ghost small" @click="exportAssets('xlsx')">导出 XLSX</button>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div class="panel table-panel">
      <table class="data">
        <thead>
          <tr>
            <th>案件名称</th>
            <th>我方文号</th>
            <th>类型</th>
            <th>综合状态</th>
            <th>授权公告日</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>
              <RouterLink :to="`/assets/${item.id}`" class="name-link">
                <strong>{{ item.name }}</strong>
              </RouterLink>
            </td>
            <td>{{ item.docket_no || '—' }}</td>
            <td>{{ typeLabels[item.ip_type] }}</td>
            <td><span class="badge">{{ statusLabels[item.status_group] }}</span></td>
            <td>{{ item.grant_date ? formatDate(item.grant_date) : '—' }}</td>
            <td>{{ formatDate(item.updated_at) }}</td>
            <td>
              <div class="row-actions">
                <RouterLink :to="`/assets/${item.id}`" class="button ghost small">查看</RouterLink>
                <button v-if="canWrite" class="button ghost small" @click="openEdit(item.id)">编辑</button>
                <button v-if="canWrite" class="button ghost small danger" @click="openDelete(item)">删除</button>
              </div>
            </td>
          </tr>
          <tr v-if="!loading && items.length === 0">
            <td colspan="7" class="empty">暂无档案数据</td>
          </tr>
          <tr v-if="loading">
            <td colspan="7" class="empty">加载中…</td>
          </tr>
        </tbody>
      </table>
      <div class="pagination">
        <span>共 {{ total }} 条</span>
        <span>
          <button class="button small" :disabled="page <= 1" @click="page--; load()">上一页</button>
          <span style="margin: 0 8px">第 {{ page }} 页</span>
          <button class="button small" :disabled="page * pageSize >= total" @click="page++; load()">下一页</button>
        </span>
      </div>
    </div>

    <AssetFormDrawer
      :open="showDrawer"
      :asset-id="editingId"
      @close="showDrawer = false"
      @saved="onSaved"
    />

    <div v-if="deleteTarget" class="confirm-backdrop" @click="closeDelete">
      <section class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="delete_asset_title" @click.stop>
        <header>
          <small>删除确认</small>
          <h2 id="delete_asset_title">删除该档案？</h2>
        </header>
        <div class="confirm-body">
          <p>确定删除「<strong>{{ deleteTarget.name }}</strong>」吗？</p>
          <p class="hint">删除为逻辑删除，关联材料 / 费用 / 日期保留，历史审计可追溯。</p>
        </div>
        <footer>
          <button class="button ghost" :disabled="deleting" @click="closeDelete">取消</button>
          <button class="button danger" :disabled="deleting" @click="confirmDelete">{{ deleting ? '删除中…' : '确认删除' }}</button>
        </footer>
      </section>
    </div>
  </section>
</template>
