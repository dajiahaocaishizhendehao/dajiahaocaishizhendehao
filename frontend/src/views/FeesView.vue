<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, formatDate } from '../api'
import { formatMoney } from '../money'
import { feeLabels, feeStatusLabels } from '../labels'
import { useToast } from '../toast'
import InvoiceDialog from '../components/InvoiceDialog.vue'
import AssetPicker, { type AssetOption } from '../components/AssetPicker.vue'
import { useAuth } from '../auth'

const route = useRoute()
const { canWrite } = useAuth()
const toast = useToast()
const assetFilter = ref(String(route.query.asset || ''))
const assetLabel = ref('')

interface FeeInvoice {
  id: string
  invoice_no: string
  invoice_code: string | null
  invoice_date: string | null
  amount_gross: string | null
  currency: string
  file_material_id: string | null
}

interface FeeRow {
  id: string
  ip_asset_id: string | null
  asset_name: string | null
  docket_no: string | null
  application_no: string | null
  fee_type: string
  description: string | null
  amount_due: string
  amount_paid: string | null
  currency: string
  due_date: string | null
  paid_date: string | null
  coverage_end_date: string | null
  status: string
  invoice_count: number
}

const items = ref<FeeRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const PAGE_SIZE_OPTIONS = [20, 50, 100]
const assets = ref<AssetOption[]>([])
const loading = ref(true)
const error = ref('')
const keyword = ref('')
const showDrawer = ref(false)
const saving = ref(false)
const formError = ref('')
const editingId = ref('')
const editingDetail = ref<Record<string, unknown> | null>(null)
const deleteTarget = ref<FeeRow | null>(null)
const deleting = ref(false)

const form = reactive({
  ip_asset_id: '',
  fee_type: 'annuity',
  description: '',
  amount_due: '',
  amount_paid: '',
  due_date: '',
  paid_date: '',
  coverage_end_date: '',
  payee: '国家知识产权局',
})

const now = new Date()

const invoiceDialogOpen = ref(false)
const invoiceDialogFee = ref<FeeRow | null>(null)

function openInvoiceDialog(fee: FeeRow) {
  invoiceDialogFee.value = fee
  invoiceDialogOpen.value = true
}

async function onInvoiceSaved() {
  invoiceDialogOpen.value = false
  await load()
}


function daysLeft(value: string | null): number | null {
  if (!value) return null
  const target = new Date(`${value}T00:00:00`)
  const diff = target.getTime() - new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  return Math.round(diff / 86400000)
}

function coverageHint(row: FeeRow): string {
  const left = daysLeft(row.coverage_end_date)
  if (left === null) return '—'
  if (left < 0) return `已过期 ${Math.abs(left)} 天`
  return `剩余 ${left} 天`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [fees, assetPage] = await Promise.all([
      api.fees({
        q: keyword.value.trim() || undefined,
        page: page.value,
        page_size: pageSize.value,
        ...(assetFilter.value ? { ip_asset_id: assetFilter.value } : {}),
      }),
      api.assets({ page: 1, page_size: 20 }),
    ])
    items.value = fees.items as unknown as FeeRow[]
    total.value = fees.total
    assets.value = assetPage.items.map((item) => ({
      id: item.id,
      name: item.name,
      docket_no: item.docket_no,
    }))
    if (assetFilter.value) {
      try {
        assetLabel.value = (await api.asset(assetFilter.value)).name
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

async function searchAssets(query: string): Promise<AssetOption[]> {
  const result = await api.assets({ q: query, page: 1, page_size: 20 })
  return result.items.map((item) => ({
    id: item.id,
    name: item.name,
    docket_no: item.docket_no,
  }))
}

function query() {
  page.value = 1
  void load()
}

function changePageSize() {
  page.value = 1
  void load()
}

function clearFilter() {
  assetFilter.value = ''
  assetLabel.value = ''
  keyword.value = ''
  page.value = 1
  void load()
}

function openCreate() {
  formError.value = ''
  editingId.value = ''
  editingDetail.value = null
  Object.assign(form, {
    ip_asset_id: '',
    fee_type: 'annuity',
    description: '',
    amount_due: '',
    amount_paid: '',
    due_date: '',
    paid_date: '',
    coverage_end_date: '',
    payee: '国家知识产权局',
  })
  showDrawer.value = true
}

async function openEdit(fee: FeeRow) {
  formError.value = ''
  editingId.value = fee.id
  editingDetail.value = null
  try {
    editingDetail.value = await api.fee(fee.id)
  } catch {
    editingDetail.value = null
  }
  const detail = editingDetail.value
  Object.assign(form, {
    ip_asset_id: fee.ip_asset_id ?? '',
    fee_type: fee.fee_type,
    description: fee.description ?? '',
    amount_due: fee.amount_due ?? '',
    amount_paid: fee.amount_paid ?? '',
    due_date: fee.due_date ?? '',
    paid_date: fee.paid_date ?? '',
    coverage_end_date: fee.coverage_end_date ?? '',
    payee: (detail?.payee as string | null) ?? '国家知识产权局',
  })
  // 确保当前案件出现在选择器中，避免编辑时选择器显示为空
  if (fee.ip_asset_id && detail && !assets.value.some((a) => a.id === fee.ip_asset_id)) {
    assets.value.push({
      id: fee.ip_asset_id,
      name: (detail.asset_name as string) || '未命名案件',
      docket_no: (detail.docket_no as string | null) ?? null,
    })
  }
  showDrawer.value = true
}

function openDelete(fee: FeeRow) {
  deleteTarget.value = fee
}

function closeDelete() {
  if (deleting.value) return
  deleteTarget.value = null
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await api.deleteFee(deleteTarget.value.id)
    deleteTarget.value = null
    toast.success('费用已删除')
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败'
    deleteTarget.value = null
  } finally {
    deleting.value = false
  }
}

async function save() {
  formError.value = ''
  if (!form.ip_asset_id) {
    formError.value = '请选择案件'
    return
  }
  if (!form.amount_due) {
    formError.value = '应缴金额必填'
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      const detail = editingDetail.value ?? {}
      const payload: Record<string, unknown> = {
        ip_asset_id: form.ip_asset_id || null,
        fee_type: form.fee_type,
        description: form.description || null,
        amount_due: form.amount_due,
        amount_paid: form.amount_paid || null,
        currency: (detail.currency as string) || 'CNY',
        due_date: form.due_date || null,
        paid_date: form.paid_date || null,
        coverage_end_date: form.coverage_end_date || null,
        payee: form.payee || null,
        payer: (detail.payer as string | null) ?? null,
        payment_method: (detail.payment_method as string | null) ?? null,
        voucher_material_id: (detail.voucher_material_id as string | null) ?? null,
        handler: (detail.handler as string | null) ?? null,
        remark: (detail.remark as string | null) ?? null,
      }
      if (detail.status === 'canceled') payload.status = 'canceled'
      await api.updateFee(editingId.value, payload)
    } else {
      await api.createFee({
        ip_asset_id: form.ip_asset_id,
        fee_type: form.fee_type,
        description: form.description || null,
        amount_due: form.amount_due,
        amount_paid: form.amount_paid || null,
        currency: 'CNY',
        due_date: form.due_date || null,
        paid_date: form.paid_date || null,
        coverage_end_date: form.coverage_end_date || null,
        payee: form.payee || null,
      })
    }
    const wasEdit = Boolean(editingId.value)
    showDrawer.value = false
    editingId.value = ''
    editingDetail.value = null
    form.amount_due = ''
    form.amount_paid = ''
    toast.success(wasEdit ? '费用已保存' : '费用已登记')
    await load()
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await load()
  if (route.query.create === '1') openCreate()
})
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h1>费用台账</h1>
        <p>按案件名称查看年费应缴、实缴与缴至日期；金额不做跨口径相加</p>
      </div>
    </div>

    <div class="toolbar">
      <button v-if="canWrite" class="button primary" @click="openCreate">＋ 登记费用</button>
      <input v-model="keyword" class="field" placeholder="搜索案件名称 / 我方文号 / 申请号" style="width: 280px" @keyup.enter="query" />
      <button class="button small" @click="query">查询</button>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div v-if="assetFilter" class="panel" style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center">
      <span>仅显示案件：<strong>{{ assetLabel || assetFilter }}</strong></span>
      <button class="button ghost small" @click="clearFilter">查看全部</button>
    </div>

    <div class="panel table-panel">
      <table class="data">
        <thead>
          <tr>
            <th>案件名称</th>
            <th>我方文号</th>
            <th>申请号</th>
            <th>类别</th>
            <th>应缴日</th>
            <th>已缴至</th>
            <th>金额</th>
            <th>缴纳日期</th>
            <th>状态</th>
            <th>发票</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td style="min-width: 240px">
              <RouterLink :to="`/fees/${item.id}`" class="name-link">
                <strong>{{ item.asset_name || '未关联案件' }}</strong>
              </RouterLink>
            </td>
            <td>{{ item.docket_no || '—' }}</td>
            <td>{{ item.application_no || '—' }}</td>
            <td>{{ feeLabels[item.fee_type] ?? item.fee_type }}</td>
            <td>{{ formatDate(item.due_date) }}</td>
            <td>
              {{ formatDate(item.coverage_end_date) }}
              <span class="badge" :class="daysLeft(item.coverage_end_date) !== null && daysLeft(item.coverage_end_date)! < 90 ? 'amber' : 'green'">
                {{ coverageHint(item) }}
              </span>
            </td>
            <td>{{ formatMoney(item.amount_due, item.currency) }}</td>
            <td>{{ formatDate(item.paid_date) }}</td>
            <td>
              <span class="badge" :class="item.status === 'paid' ? 'green' : item.status === 'partial' ? 'amber' : 'gray'">
                {{ feeStatusLabels[item.status] ?? item.status }}
              </span>
            </td>
            <td>
              <div class="row-actions">
                <button v-if="canWrite" class="button ghost small" @click="openEdit(item)">编辑</button>
                <button v-if="canWrite" class="button ghost small danger" @click="openDelete(item)">删除</button>
                <RouterLink
                  v-if="item.invoice_count > 0"
                  :to="`/fees/${item.id}`"
                  class="button ghost small"
                >
                  {{ item.invoice_count }} 张
                </RouterLink>
                <button v-else-if="canWrite" class="button ghost small" @click="openInvoiceDialog(item)">登记发票</button>
              </div>
            </td>
          </tr>
          <tr v-if="loading">
            <td colspan="10" class="empty">加载中…</td>
          </tr>
          <tr v-else-if="items.length === 0">
            <td colspan="10" class="empty">暂无费用记录</td>
          </tr>
        </tbody>
      </table>
      <div class="pagination">
        <span>
          共 {{ total }} 条
          <span class="page-size">
            · 每页
            <select v-model.number="pageSize" aria-label="每页显示条数" @change="changePageSize">
              <option v-for="size in PAGE_SIZE_OPTIONS" :key="size" :value="size">{{ size }}</option>
            </select>
            条
          </span>
        </span>
        <span>
          <button class="button small" :disabled="page <= 1 || loading" @click="page--; load()">上一页</button>
          <span style="margin: 0 8px">第 {{ page }} 页</span>
          <button class="button small" :disabled="page * pageSize >= total || loading" @click="page++; load()">下一页</button>
        </span>
      </div>
    </div>

    <InvoiceDialog
      v-if="canWrite"
      :open="invoiceDialogOpen"
      :asset-id="invoiceDialogFee?.ip_asset_id ?? ''"
      :fee-id="invoiceDialogFee?.id ?? ''"
      @close="invoiceDialogOpen = false"
      @saved="onInvoiceSaved"
    />

    <div v-if="showDrawer">
      <div class="drawer-backdrop" @click="showDrawer = false"></div>
      <aside
        class="drawer"
        role="dialog"
        aria-modal="true"
        :aria-label="editingId ? '编辑费用' : '登记费用'"
        tabindex="-1"
        @keydown.esc="showDrawer = false"
      >
        <header>
          <small>费用台账</small>
          <h2>{{ editingId ? '编辑费用' : '登记费用' }}</h2>
        </header>
        <div class="drawer-body">
          <div class="form-grid">
            <div class="form-item full">
              <label>关联案件 *</label>
              <AssetPicker
                v-model="form.ip_asset_id"
                :assets="assets"
                :search="searchAssets"
                placeholder="输入案件名称或我方文号搜索（必选）"
              />
            </div>
            <div class="form-item">
              <label for="f_type">费用类型</label>
              <select id="f_type" v-model="form.fee_type">
                <option v-for="(label, value) in feeLabels" :key="value" :value="value">{{ label }}</option>
              </select>
            </div>
            <div class="form-item">
              <label for="f_due">官费应缴日</label>
              <input id="f_due" v-model="form.due_date" type="date" />
            </div>
            <div class="form-item">
              <label for="f_amount">应缴金额 *</label>
              <input id="f_amount" v-model="form.amount_due" inputmode="decimal" placeholder="0.00" />
            </div>
            <div class="form-item">
              <label for="f_paid">实缴金额</label>
              <input id="f_paid" v-model="form.amount_paid" inputmode="decimal" placeholder="未支付可留空" />
            </div>
            <div class="form-item">
              <label for="f_paid_date">缴纳日期</label>
              <input id="f_paid_date" v-model="form.paid_date" type="date" />
            </div>
            <div class="form-item">
              <label for="f_coverage">本次缴费缴至</label>
              <input id="f_coverage" v-model="form.coverage_end_date" type="date" />
            </div>
            <div class="form-item full">
              <label for="f_desc">说明</label>
              <input id="f_desc" v-model="form.description" placeholder="例如：第 3 年年费" />
            </div>
          </div>
          <p v-if="formError" class="error-text" style="margin-top: 12px">{{ formError }}</p>
          <p class="hint" style="margin-top: 12px">应缴日、实缴日与缴至日是三个不同概念，分别记录。</p>
        </div>
        <footer>
          <button class="button ghost" @click="showDrawer = false">取消</button>
          <button class="button primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </footer>
      </aside>
    </div>

    <div v-if="deleteTarget" class="confirm-backdrop" @click="closeDelete">
      <section class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="delete_fee_title" @click.stop>
        <header>
          <small>删除确认</small>
          <h2 id="delete_fee_title">删除该笔费用？</h2>
        </header>
        <div class="confirm-body">
          <p>确定删除「<strong>{{ deleteTarget.asset_name || '未关联案件' }}</strong>」的{{ feeLabels[deleteTarget.fee_type] ?? deleteTarget.fee_type }}费用吗？</p>
          <p class="hint">删除为逻辑删除，关联发票不受影响，历史记录保留。</p>
        </div>
        <footer>
          <button class="button ghost" :disabled="deleting" @click="closeDelete">取消</button>
          <button class="button danger" :disabled="deleting" @click="confirmDelete">{{ deleting ? '删除中…' : '确认删除' }}</button>
        </footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.page-size select {
  margin: 0 4px;
  padding: 2px 4px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #fff;
  font-size: 12px;
  color: inherit;
}
</style>
