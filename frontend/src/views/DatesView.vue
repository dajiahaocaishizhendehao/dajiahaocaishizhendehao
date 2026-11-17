<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, formatDate, type DateItem } from '../api'
import { dateSourceLabels, dateStatusLabels, dateTypeLabels } from '../labels'
import { useAuth } from '../auth'
import { useToast } from '../toast'
import AssetPicker, { type AssetOption } from '../components/AssetPicker.vue'

const route = useRoute()
const { canWrite } = useAuth()
const toast = useToast()
const assetFilter = ref(String(route.query.asset || ''))
const assetLabel = ref('')
const items = ref<DateItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(true)
const error = ref('')
const showDrawer = ref(false)
const saving = ref(false)
const formError = ref('')
const editingId = ref('')
const editAssetName = ref('')
const cancelTarget = ref<DateItem | null>(null)
const canceling = ref(false)
const assets = ref<AssetOption[]>([])
const focusId = String(route.query.focus || '')
const focusedRow = ref<HTMLElement | null>(null)
const view = ref<'list' | 'calendar'>('list')
const calCursor = ref(new Date())
const calItems = ref<DateItem[]>([])
const calLoading = ref(false)

async function searchAssets(query: string): Promise<AssetOption[]> {
  const result = await api.assets({ q: query, page: 1, page_size: 20 })
  return result.items.map((item) => ({ id: item.id, name: item.name, docket_no: item.docket_no }))
}

const form = reactive({
  title: '',
  date_type: 'due',
  due_date: '',
  planned_date: '',
  ip_asset_id: '',
  remark: '',
})

async function load() {
  loading.value = true
  try {
    const result = await api.dates({
      page: page.value,
      page_size: pageSize,
      ...(assetFilter.value ? { ip_asset_id: assetFilter.value } : {}),
    })
    items.value = result.items
    total.value = result.total
    if (focusId && result.items.some((item) => item.id === focusId)) {
      await nextTick()
      focusedRow.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    if (assetFilter.value) {
      try {
        const target = await api.asset(assetFilter.value)
        assetLabel.value = target.name
      } catch {
        assetLabel.value = ''
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function clearFilter() {
  assetFilter.value = ''
  assetLabel.value = ''
  page.value = 1
  void load()
}

function openCreate() {
  formError.value = ''
  editingId.value = ''
  editAssetName.value = ''
  form.title = ''
  form.date_type = 'due'
  form.due_date = ''
  form.planned_date = ''
  form.ip_asset_id = ''
  form.remark = ''
  showDrawer.value = true
}

function openEdit(item: DateItem) {
  formError.value = ''
  editingId.value = item.id
  editAssetName.value = item.asset_name ?? ''
  form.title = item.title
  form.date_type = item.date_type
  form.due_date = item.due_date ?? ''
  form.planned_date = item.planned_date ?? ''
  form.ip_asset_id = item.ip_asset_id ?? ''
  form.remark = item.remark ?? ''
  showDrawer.value = true
}

function openCancel(item: DateItem) {
  cancelTarget.value = item
}

function closeCancel() {
  if (canceling.value) return
  cancelTarget.value = null
}

async function confirmCancel() {
  if (!cancelTarget.value) return
  canceling.value = true
  try {
    await api.updateDate(cancelTarget.value.id, { status: 'canceled' })
    cancelTarget.value = null
    toast.success('事项已作废')
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '操作失败'
    cancelTarget.value = null
  } finally {
    canceling.value = false
  }
}

async function save() {
  formError.value = ''
  if (!form.title.trim()) {
    formError.value = '事项名称必填'
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.updateDate(editingId.value, {
        title: form.title.trim(),
        date_type: form.date_type,
        due_date: form.due_date || null,
        planned_date: form.planned_date || null,
        remark: form.remark.trim() || null,
      })
    } else {
      await api.createDate({
        title: form.title.trim(),
        date_type: form.date_type,
        due_date: form.due_date || null,
        planned_date: form.planned_date || null,
        ip_asset_id: form.ip_asset_id || null,
        source: 'manual',
        remark: form.remark || null,
      })
    }
    const wasEdit = Boolean(editingId.value)
    showDrawer.value = false
    editingId.value = ''
    editAssetName.value = ''
    form.title = ''
    form.due_date = ''
    toast.success(wasEdit ? '已保存' : '已新建')
    await load()
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function complete(id: string) {
  try {
    await api.completeDate(id)
    toast.success('已标记完成')
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '操作失败'
  }
}

function fmtDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

async function loadCalendar() {
  calLoading.value = true
  const year = calCursor.value.getFullYear()
  const month = calCursor.value.getMonth()
  const from = fmtDay(new Date(year, month, 1))
  const to = fmtDay(new Date(year, month + 1, 0))
  try {
    const result = await api.dates({ due_from: from, due_to: to, page: 1, page_size: 200 })
    calItems.value = result.items
  } catch {
    calItems.value = []
  } finally {
    calLoading.value = false
  }
}

function changeMonth(delta: number) {
  calCursor.value = new Date(calCursor.value.getFullYear(), calCursor.value.getMonth() + delta, 1)
  void loadCalendar()
}

function openCalendar() {
  view.value = 'calendar'
  void loadCalendar()
}

const calendarDays = computed(() => {
  const year = calCursor.value.getFullYear()
  const month = calCursor.value.getMonth()
  const first = new Date(year, month, 1)
  const offset = (first.getDay() + 6) % 7 // 周一起始
  const start = new Date(year, month, 1 - offset)
  const byDate = new Map<string, DateItem[]>()
  for (const item of calItems.value) {
    const key = (item.due_date || item.planned_date || '').slice(0, 10)
    if (!key) continue
    const list = byDate.get(key) ?? []
    list.push(item)
    byDate.set(key, list)
  }
  const days: Array<{ key: string; day: number; inMonth: boolean; items: DateItem[] }> = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i)
    const key = fmtDay(d)
    days.push({ key, day: d.getDate(), inMonth: d.getMonth() === month, items: byDate.get(key) ?? [] })
  }
  return days
})

function calBadgeClass(item: DateItem): string {
  if (item.status === 'done') return 'green'
  if (item.status === 'canceled') return 'gray'
  const due = item.due_date || item.planned_date
  if (!due) return ''
  const today = new Date()
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
  const target = new Date(`${due.slice(0, 10)}T00:00:00`).getTime()
  const diff = Math.round((target - t) / 86400000)
  if (diff < 0) return 'red'
  if (diff <= 7) return 'amber'
  return ''
}

onMounted(async () => {
  try {
    const result = await api.assets({ page: 1, page_size: 20 })
    assets.value = result.items.map((item) => ({ id: item.id, name: item.name, docket_no: item.docket_no }))
  } catch {
    assets.value = []
  }
  await load()
})
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h1>日期台账</h1>
        <p>计划、截止、完成与提醒时间分别记录；系统不自动给出法律结论</p>
      </div>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: view === 'list' }" @click="view = 'list'">列表</button>
      <button class="tab" :class="{ active: view === 'calendar' }" @click="openCalendar">日历</button>
    </div>

    <template v-if="view === 'list'">
    <div class="toolbar">
      <button v-if="canWrite" class="button primary" @click="openCreate">＋ 新建日期事项</button>
    </div>

    <div v-if="assetFilter" class="panel" style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center">
      <span>仅显示案件：<strong>{{ assetLabel || assetFilter }}</strong></span>
      <button class="button ghost small" @click="clearFilter">查看全部</button>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div class="panel table-panel">
      <table class="data">
        <thead>
          <tr>
            <th>事项名称</th>
            <th>关联案件</th>
            <th>日期类型</th>
            <th>计划 / 截止</th>
            <th>实际完成</th>
            <th>状态</th>
            <th>来源</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in items"
            :key="item.id"
            :ref="(el) => { if (item.id === focusId) focusedRow = el as HTMLElement }"
            :class="{ 'focused-row': item.id === focusId }"
          >
            <td>{{ item.title }}</td>
            <td style="min-width: 180px">
              <RouterLink v-if="item.ip_asset_id" :to="`/assets/${item.ip_asset_id}`" class="name-link">
                {{ item.asset_name || '未命名案件' }}
              </RouterLink>
              <span v-else class="hint">未关联案件</span>
            </td>
            <td>{{ dateTypeLabels[item.date_type] ?? item.date_type }}</td>
            <td>{{ formatDate(item.due_date || item.planned_date) }}</td>
            <td>{{ formatDate(item.actual_date) }}</td>
            <td>
              <span class="badge" :class="item.status === 'done' ? 'green' : item.status === 'canceled' ? 'gray' : 'amber'">
                {{ dateStatusLabels[item.status] ?? item.status }}
              </span>
            </td>
            <td>{{ dateSourceLabels[item.source] ?? item.source }}</td>
            <td>
              <div class="row-actions">
                <button v-if="canWrite" class="button ghost small" @click="openEdit(item)">编辑</button>
                <button v-if="canWrite && item.status === 'open'" class="button ghost small" @click="complete(item.id)">标记完成</button>
                <button v-if="canWrite && item.status === 'open'" class="button ghost small danger" @click="openCancel(item)">作废</button>
              </div>
            </td>
          </tr>
          <tr v-if="loading">
            <td colspan="8" class="empty">加载中…</td>
          </tr>
          <tr v-else-if="items.length === 0">
            <td colspan="8" class="empty">暂无日期事项</td>
          </tr>
        </tbody>
      </table>
      <div class="pagination">
        <span>共 {{ total }} 条</span>
        <span>
          <button class="button small" :disabled="page <= 1 || loading" @click="page--; load()">上一页</button>
          <span style="margin: 0 8px">第 {{ page }} 页</span>
          <button class="button small" :disabled="page * pageSize >= total || loading" @click="page++; load()">下一页</button>
        </span>
      </div>
    </div>
    </template>

    <template v-if="view === 'calendar'">
      <div class="panel">
        <div class="cal-head">
          <button class="button small" @click="changeMonth(-1)">‹ 上月</button>
          <strong>{{ calCursor.getFullYear() }} 年 {{ calCursor.getMonth() + 1 }} 月</strong>
          <button class="button small" @click="changeMonth(1)">下月 ›</button>
        </div>
        <p v-if="calLoading" class="hint">加载中…</p>
        <div class="cal-grid">
          <div v-for="w in ['周一', '周二', '周三', '周四', '周五', '周六', '周日']" :key="w" class="cal-cell cal-weekday">{{ w }}</div>
          <div v-for="day in calendarDays" :key="day.key" class="cal-cell" :class="{ 'cal-out': !day.inMonth }">
            <div class="cal-day">{{ day.day }}</div>
            <button v-for="item in day.items.slice(0, 3)" :key="item.id" class="cal-item" @click="openEdit(item)">
              <span class="badge" :class="calBadgeClass(item)">{{ item.title }}</span>
            </button>
            <span v-if="day.items.length > 3" class="hint">+{{ day.items.length - 3 }}</span>
          </div>
        </div>
      </div>
    </template>

    <div v-if="showDrawer">
      <div class="drawer-backdrop" @click="showDrawer = false"></div>
      <aside class="drawer" role="dialog" aria-modal="true" :aria-label="editingId ? '编辑日期事项' : '新建日期事项'">
        <header>
          <small>日期与提醒</small>
          <h2>{{ editingId ? '编辑日期事项' : '新建日期事项' }}</h2>
        </header>
        <div class="drawer-body">
          <div class="form-grid">
            <div class="form-item full">
              <label for="d_title">事项名称 *</label>
              <input id="d_title" v-model="form.title" placeholder="例如 软著补正材料提交" />
            </div>
            <div class="form-item">
              <label for="d_type">日期类型</label>
              <select id="d_type" v-model="form.date_type">
                <option value="planned">计划日期</option>
                <option value="due">截止日期</option>
                <option value="actual">实际完成日期</option>
                <option value="custom">自定义</option>
              </select>
            </div>
            <div class="form-item">
              <label for="d_due">计划 / 截止日期</label>
              <input id="d_due" v-model="form.due_date" type="date" />
            </div>
            <div class="form-item">
              <label>关联案件</label>
              <AssetPicker
                v-if="!editingId"
                v-model="form.ip_asset_id"
                :assets="assets"
                :search="searchAssets"
                placeholder="输入案件名称或我方文号搜索（可留空）"
              />
              <div v-else>
                <RouterLink v-if="form.ip_asset_id" :to="`/assets/${form.ip_asset_id}`" class="name-link">
                  {{ editAssetName || '查看案件' }}
                </RouterLink>
                <span v-else class="hint">未关联案件</span>
                <p class="hint" style="margin: 4px 0 0">编辑时不可变更关联案件</p>
              </div>
            </div>
            <div class="form-item full">
              <label for="d_remark">备注</label>
              <textarea id="d_remark" v-model="form.remark" placeholder="记录依据或人工确认说明"></textarea>
            </div>
          </div>
          <p v-if="formError" class="error-text" style="margin-top: 12px">{{ formError }}</p>
        </div>
        <footer>
          <button class="button ghost" @click="showDrawer = false">取消</button>
          <button class="button primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </footer>
      </aside>
    </div>

    <div v-if="cancelTarget" class="confirm-backdrop" @click="closeCancel">
      <section class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="cancel_date_title" @click.stop>
        <header>
          <small>作废确认</small>
          <h2 id="cancel_date_title">作废该日期事项？</h2>
        </header>
        <div class="confirm-body">
          <p>确定作废「<strong>{{ cancelTarget.title }}</strong>」吗？</p>
          <p class="hint">作废后该事项不再触发提醒，历史记录保留。</p>
        </div>
        <footer>
          <button class="button ghost" :disabled="canceling" @click="closeCancel">取消</button>
          <button class="button danger" :disabled="canceling" @click="confirmCancel">{{ canceling ? '作废中…' : '确认作废' }}</button>
        </footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.focused-row { background: #fff5df !important; outline: 2px solid #e8ad4a; outline-offset: -2px; }
.cal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.cal-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; }
.cal-cell { min-height: 96px; border: 1px solid var(--line); border-radius: 8px; padding: 6px; background: #fff; }
.cal-cell.cal-weekday { min-height: auto; border: 0; background: transparent; color: var(--muted); font-size: 12px; font-weight: 600; }
.cal-cell.cal-out { opacity: .45; background: #fafbfc; }
.cal-day { font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.cal-item { display: block; width: 100%; border: 0; background: transparent; padding: 0; text-align: left; margin-bottom: 2px; cursor: pointer; }
.cal-item .badge { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; }
</style>
