<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, formatDate } from '../api'
import { formatMoney } from '../money'
import { reimbursementLabels } from '../labels'
import { useAuth } from '../auth'
import { useToast } from '../toast'
import InvoiceDialog from '../components/InvoiceDialog.vue'

interface InvoiceRow {
  id: string
  invoice_no: string
  invoice_code: string | null
  issuer: string | null
  buyer: string | null
  invoice_date: string | null
  amount_gross: string | null
  currency: string
  reimbursement_status: string
  file_material_id: string | null
  ip_asset_id: string | null
  asset_name: string | null
  docket_no: string | null
  fee_ids: string[]
}

const { canWrite } = useAuth()
const toast = useToast()

const items = ref<InvoiceRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(true)
const error = ref('')
const keyword = ref('')
const dialogOpen = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await api.invoices({
      q: keyword.value.trim() || undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = result.items as unknown as InvoiceRow[]
    total.value = result.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function query() {
  page.value = 1
  void load()
}

function reset() {
  keyword.value = ''
  page.value = 1
  void load()
}

async function downloadAttachment(invoice: InvoiceRow) {
  if (!invoice.file_material_id) return
  try {
    await api.downloadMaterialFile(invoice.file_material_id, `${invoice.invoice_no}.pdf`)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '附件下载失败')
  }
}

function onInvoiceSaved() {
  dialogOpen.value = false
  toast.success('发票已登记')
  void load()
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h1>发票台账</h1>
        <p>集中登记与查询发票；关联费用在登记时勾选，一张发票可关联多笔费用</p>
      </div>
    </div>

    <div class="toolbar">
      <button v-if="canWrite" class="button primary" @click="dialogOpen = true">＋ 登记发票</button>
      <input v-model="keyword" class="field" placeholder="搜索发票号 / 开票方 / 案件名称" style="width: 300px" @keyup.enter="query" />
      <button class="button small" @click="query">查询</button>
      <button class="button ghost small" @click="reset">重置</button>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div class="panel table-panel">
      <table class="data">
        <thead>
          <tr>
            <th>发票号码</th>
            <th>发票代码</th>
            <th>案件名称</th>
            <th>开票方</th>
            <th>开票日期</th>
            <th>价税合计</th>
            <th>报销状态</th>
            <th>关联费用</th>
            <th>附件</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td><strong>{{ item.invoice_no }}</strong></td>
            <td>{{ item.invoice_code || '—' }}</td>
            <td style="min-width: 220px">
              <RouterLink v-if="item.ip_asset_id" :to="`/assets/${item.ip_asset_id}`" class="name-link">
                {{ item.asset_name || '未命名案件' }}
              </RouterLink>
              <span v-else class="hint">未关联案件</span>
            </td>
            <td>{{ item.issuer || '—' }}</td>
            <td>{{ formatDate(item.invoice_date) }}</td>
            <td>{{ formatMoney(item.amount_gross, item.currency) }}</td>
            <td>
              <span class="badge" :class="item.reimbursement_status === 'done' ? 'green' : item.reimbursement_status === 'pending' ? 'amber' : 'gray'">
                {{ reimbursementLabels[item.reimbursement_status] ?? item.reimbursement_status }}
              </span>
            </td>
            <td>{{ item.fee_ids.length }} 笔</td>
            <td>
              <button v-if="item.file_material_id" class="button ghost small" @click="downloadAttachment(item)">下载</button>
              <span v-else class="hint">—</span>
            </td>
          </tr>
          <tr v-if="loading">
            <td colspan="9" class="empty">加载中…</td>
          </tr>
          <tr v-else-if="items.length === 0">
            <td colspan="9" class="empty">暂无发票</td>
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

    <InvoiceDialog
      v-if="canWrite"
      :open="dialogOpen"
      @close="dialogOpen = false"
      @saved="onInvoiceSaved"
    />
  </section>
</template>
