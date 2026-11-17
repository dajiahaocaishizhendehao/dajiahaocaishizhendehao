<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, formatDate, type AssetListItem, type Workbench } from '../api'
import { formatMoney } from '../money'
import { dateTypeLabels, feeLabels, typeLabels } from '../labels'
import { useToast } from '../toast'
import ImportDialog from '../components/ImportDialog.vue'
import { useAuth } from '../auth'

const router = useRouter()
const { canWrite } = useAuth()
const toast = useToast()
const data = ref<Workbench | null>(null)
const loading = ref(true)
const error = ref('')
const windowDays = ref(30)
const taskFilter = ref<'all' | 'week' | 'overdue'>('all')
const searchText = ref('')
const searchResults = ref<AssetListItem[]>([])
const searching = ref(false)
const importOpen = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | null = null
let searchGeneration = 0

const filteredTasks = computed(() => {
  const tasks = data.value?.tasks ?? []
  if (taskFilter.value === 'overdue') return tasks.filter((item) => item.days_left < 0)
  if (taskFilter.value === 'week') return tasks.filter((item) => item.days_left >= 0 && item.days_left <= 7)
  return tasks
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.workbench(windowDays.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '工作台加载失败'
  } finally {
    loading.value = false
  }
}

function scheduleSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  const query = searchText.value.trim()
  const generation = ++searchGeneration
  if (!query) {
    searchResults.value = []
    searching.value = false
    return
  }
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      const items = (await api.assets({ q: query, page: 1, page_size: 8 })).items
      if (generation === searchGeneration) searchResults.value = items
    } catch {
      if (generation === searchGeneration) searchResults.value = []
    } finally {
      if (generation === searchGeneration) searching.value = false
    }
  }, 250)
}

function openAsset(id: string) {
  searchText.value = ''
  searchResults.value = []
  void router.push(`/assets/${id}`)
}

function openNewAsset() {
  void router.push({ path: '/assets', query: { create: '1' } })
}

function openMaterials() { void router.push({ path: '/materials', query: { upload: '1' } }) }
async function onImported(created: number) {
  toast.success(`成功导入 ${created} 条档案`)
  await load()
}
function openFees() { void router.push({ path: '/fees', query: { create: '1' } }) }
function openFee(id: string) { void router.push(`/fees/${id}`) }

function taskDateHint(days: number): string {
  if (days < 0) return `逾期 ${Math.abs(days)} 天`
  if (days === 0) return '今天'
  return `剩余 ${days} 天`
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h1>知识产权工作台</h1>
        <p>集中处理待办、缺少发票的费用和需要确认的材料</p>
      </div>
    </div>

    <div class="toolbar">
      <div class="search-input-wrap">
        <input
          v-model="searchText"
          class="field"
          placeholder="搜索案件名称、我方文号…"
          aria-label="全局案件搜索"
          @input="scheduleSearch"
          @keyup.enter="scheduleSearch"
        />
        <div v-if="searchText.trim()" class="search-dropdown" role="listbox">
          <p v-if="searching" class="search-empty" role="status">搜索中…</p>
          <button v-for="item in searchResults" :key="item.id" class="search-result" role="option" @click="openAsset(item.id)">
            <span><strong>{{ item.name }}</strong><small>{{ typeLabels[item.ip_type] }} · {{ item.docket_no || '—' }}</small></span>
            <span class="search-action">查看案件</span>
          </button>
          <p v-if="!searching && searchResults.length === 0" class="search-empty">没有匹配案件</p>
        </div>
      </div>
      <button v-if="canWrite" class="button" @click="openNewAsset">＋ 新建案件</button>
      <button v-if="canWrite" class="button" @click="openMaterials">⇧ 上传材料</button>
      <button v-if="canWrite" class="button" @click="importOpen = true">⇧ 导入档案</button>
      <button v-if="canWrite" class="button primary" @click="openFees">¥ 登记费用</button>
    </div>

    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <p v-if="loading" class="hint" role="status">工作台加载中…</p>

    <template v-if="data">
      <section class="workbench-metrics">
        <article class="metric-card"><span>全部档案</span><strong>{{ data.total_assets }}</strong></article>
        <article class="metric-card"><span>办理中</span><strong>{{ data.in_progress_assets }}</strong></article>
        <article class="metric-card"><span>待处理日期</span><strong>{{ data.pending_date_count }}</strong></article>
        <article class="metric-card"><span>缺少发票费用</span><strong>{{ data.missing_invoice_fee_count }}</strong></article>
        <article class="metric-card"><span>识别待处理</span><strong>{{ data.extraction_attention_count }}</strong></article>
      </section>

      <section class="workbench-layout">
        <div class="workbench-stack">
          <article class="panel">
            <div class="panel-head">
              <div><h2>待处理事项</h2><p>已逾期 + 未来 {{ data.due_soon_days }} 天，仅未完成日期事项</p></div>
              <RouterLink to="/dates" class="link-button">查看日期台账 →</RouterLink>
            </div>
            <div class="workbench-tabs" role="tablist" aria-label="待办筛选">
              <button class="tab-chip" :class="{ active: taskFilter === 'all' }" role="tab" :aria-selected="taskFilter === 'all'" @click="taskFilter = 'all'">全部</button>
              <button class="tab-chip" :class="{ active: taskFilter === 'week' }" role="tab" :aria-selected="taskFilter === 'week'" @click="taskFilter = 'week'">7 天内</button>
              <button class="tab-chip" :class="{ active: taskFilter === 'overdue' }" role="tab" :aria-selected="taskFilter === 'overdue'" @click="taskFilter = 'overdue'">已逾期</button>
            </div>
            <div v-if="filteredTasks.length === 0" class="empty">当前筛选下没有待处理事项</div>
            <div v-for="item in filteredTasks" :key="item.id" class="work-row task-row">
              <div class="row-date"><strong>{{ formatDate(item.due_date) }}</strong><small :class="item.days_left < 0 ? 'danger' : ''">{{ taskDateHint(item.days_left) }}</small></div>
              <div class="row-main"><strong>{{ item.title }}</strong><small>{{ item.asset_name || '未关联案件' }}</small></div>
              <span class="badge" :class="item.days_left < 0 ? 'red' : item.days_left <= 7 ? 'amber' : ''">{{ dateTypeLabels[item.date_type] ?? item.date_type }}</span>
              <RouterLink :to="{ path: '/dates', query: { focus: item.id } }" class="button small">处理</RouterLink>
            </div>
          </article>

          <article class="panel">
            <div class="panel-head">
              <div><h2>费用与发票待对账</h2><p>已支付或部分支付，但尚未关联有效发票</p></div>
              <RouterLink to="/fees" class="link-button">查看费用台账 →</RouterLink>
            </div>
            <div v-if="data.missing_invoice_fees.length === 0" class="empty">暂无缺少发票的费用</div>
            <div v-for="fee in data.missing_invoice_fees" :key="fee.id" class="work-row fee-row">
              <div class="row-date"><strong>{{ formatMoney(fee.amount_paid || fee.amount_due, fee.currency) }}</strong><small>{{ formatDate(fee.paid_date) }}</small></div>
              <div class="row-main"><strong>{{ fee.asset_name }}</strong><small>{{ feeLabels[fee.fee_type] ?? fee.fee_type }} · {{ fee.docket_no || '无我方文号' }}</small></div>
              <span class="badge amber">未登记发票</span>
              <button class="button small" @click="openFee(fee.id)">登记发票</button>
            </div>
          </article>
        </div>

        <aside class="workbench-stack">
          <article class="panel">
            <div class="panel-head"><div><h2>材料处理</h2><p>OCR 结果必须人工确认</p></div><RouterLink to="/materials" class="link-button">材料中心 →</RouterLink></div>
            <div v-if="data.extraction_attention.length === 0" class="empty compact">暂无待处理材料</div>
            <RouterLink v-for="item in data.extraction_attention" :key="item.id" :to="{ path: '/materials', query: { focus: item.id } }" class="attention-row">
              <span class="attention-icon" :class="item.extraction_status === 'failed' ? 'failed' : ''">{{ item.extraction_status === 'failed' ? '×' : '!' }}</span>
              <span><strong>{{ item.display_name }}</strong><small>{{ item.asset_name || '未关联案件' }} · {{ item.extraction_status === 'failed' ? '识别失败，可重试' : '识别处理中' }}</small></span>
            </RouterLink>
          </article>

          <article class="panel">
            <div class="panel-head"><div><h2>最近更新案件</h2><p>最近修改的未删除档案</p></div><RouterLink to="/assets" class="link-button">全部档案 →</RouterLink></div>
            <div v-if="data.recent_assets.length === 0" class="empty compact">暂无案件</div>
            <RouterLink v-for="item in data.recent_assets" :key="item.id" :to="`/assets/${item.id}`" class="recent-row">
              <strong>{{ item.name }}</strong><small>{{ typeLabels[item.ip_type] }} · {{ formatDate(item.updated_at) }}</small>
            </RouterLink>
          </article>
        </aside>
      </section>
    </template>

    <ImportDialog v-if="canWrite" :open="importOpen" @close="importOpen = false" @imported="onImported" />
  </section>
</template>

<style scoped>
.search-input-wrap { position:relative;width:420px;flex:none; }
.search-input-wrap>.field { width:100%;font-size:13px; }
.search-dropdown { position:absolute;z-index:30;top:42px;left:0;right:0;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:0 16px 36px rgba(15,32,61,.16);overflow:hidden; }
.search-result { width:100%;border:0;border-bottom:1px solid #eef1f5;background:#fff;padding:10px 12px;display:flex;align-items:center;justify-content:space-between;gap:12px;text-align:left; }
.search-result:hover { background:#f7faff; }
.search-result>span:first-child { min-width:0;flex:1; }
.search-result strong,.search-result small { display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.search-result small,.search-empty { color:var(--muted);font-size:11px; }
.search-action { flex:0 0 auto;display:inline-flex;align-items:center;height:26px;padding:0 11px;border:1px solid #cfe0ff;border-radius:999px;background:#f5f9ff;color:#275fae;font-size:11px;font-weight:600;white-space:nowrap; }
.search-result:hover .search-action { background:#275fae;border-color:#275fae;color:#fff; }
.search-empty { margin:0;padding:14px;text-align:center; }
.workbench-metrics { display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:14px; }
.metric-card { background:#fff;border:1px solid var(--line);border-radius:12px;padding:13px 14px; }
.metric-card span { display:block;color:var(--muted);font-size:11px; }
.metric-card strong { display:block;font-size:23px;margin-top:5px; }
.workbench-layout { display:grid;grid-template-columns:minmax(0,1.55fr) minmax(320px,.75fr);gap:14px; }
.workbench-stack { display:grid;gap:14px;align-content:start; }
.panel-head { display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:11px; }
.panel-head h2 { font-size:15px;margin:0 0 4px; }
.panel-head p { font-size:11px;color:var(--muted);margin:0; }
.link-button { color:var(--blue);font-size:12px; }
.workbench-tabs { display:flex;gap:5px;margin-bottom:9px; }
.tab-chip { border:1px solid var(--line);border-radius:17px;background:#fff;height:29px;padding:0 11px;color:var(--muted); }
.tab-chip.active { background:#edf3ff;border-color:#cfe0ff;color:#275fae; }
.work-row { display:grid;grid-template-columns:104px minmax(0,1fr) 94px 88px;gap:11px;align-items:center;padding:10px 3px;border-bottom:1px solid #eef1f5; }
.work-row:last-child { border:0; }
.row-date strong,.row-date small,.row-main strong,.row-main small { display:block; }
.row-date small,.row-main small { color:var(--muted);font-size:11px;margin-top:3px; }
.row-date small.danger { color:var(--red); }
.row-main strong { font-size:13px; }
.attention-row { display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #eef1f5; }
.attention-row:last-child,.recent-row:last-child { border:0; }
.attention-icon { width:28px;height:28px;flex:0 0 auto;display:grid;place-items:center;border-radius:8px;background:#fff5df;color:#a9680c;font-weight:700; }
.attention-icon.failed { background:#fff0f1;color:#bd4653; }
.attention-row strong,.attention-row small,.recent-row strong,.recent-row small { display:block; }
.attention-row small,.recent-row small { color:var(--muted);font-size:11px;margin-top:3px; }
.recent-row { display:block;padding:9px 0;border-bottom:1px solid #eef1f5; }
.empty.compact { padding:24px 10px; }
@media (max-width: 1200px) {
  .workbench-metrics { grid-template-columns: repeat(3, 1fr); }
  .workbench-layout { grid-template-columns: 1fr; }
}
</style>
