<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, formatDate } from '../api'
import { centsToMoney, formatMoney, moneyToCents } from '../money'
import { feeLabels, feeStatusLabels } from '../labels'
import { useToast } from '../toast'
import InvoiceDialog from '../components/InvoiceDialog.vue'

interface FeeDetail {
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
  payee: string | null
  payer: string | null
  payment_method: string | null
  status: string
  invoice_count: number
}

interface InvoiceRow {
  id: string
  invoice_no: string
  invoice_code: string | null
  invoice_date: string | null
  issuer: string | null
  amount_net: string | null
  tax_amount: string | null
  amount_gross: string | null
  currency: string
  file_material_id: string | null
}

const route = useRoute()
const router = useRouter()
const fee = ref<FeeDetail | null>(null)
const invoices = ref<InvoiceRow[]>([])
const loading = ref(true)
const error = ref('')
const dialogOpen = ref(false)
const toast = useToast()

const invoiceSumCents = computed(() =>
  invoices.value.reduce((sum, item) => sum + moneyToCents(item.amount_gross), 0),
)
const paidAmountCents = computed(() => moneyToCents(fee.value?.amount_paid ?? fee.value?.amount_due ?? '0'))
const invoiceDiffCents = computed(() => invoiceSumCents.value - paidAmountCents.value)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const detail = await api.fee(String(route.params.id))
    fee.value = detail as unknown as FeeDetail
    const result = await api.feeInvoices(String(route.params.id))
    invoices.value = result.items as unknown as InvoiceRow[]
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function onInvoiceSaved() {
  dialogOpen.value = false
  toast.success('发票已登记')
  await load()
}

async function downloadAttachment(invoice: InvoiceRow) {
  if (!invoice.file_material_id) return
  try {
    await api.downloadMaterialFile(invoice.file_material_id, `${invoice.invoice_no}.pdf`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '附件下载失败'
  }
}

onMounted(load)
</script>

<template>
  <section>
    <p v-if="loading" class="hint">加载中…</p>
    <p v-else-if="error" class="error-text">{{ error }}</p>

    <template v-else-if="fee">
      <section class="detail-hero">
        <div>
          <span class="badge" style="background: rgba(255,255,255,.16); color: #fff">{{ feeStatusLabels[fee.status] ?? fee.status }}</span>
          <h1 style="margin-top: 10px">{{ fee.asset_name || '费用详情' }}</h1>
          <div class="detail-meta">
            <span>{{ feeLabels[fee.fee_type] ?? fee.fee_type }}</span>
            <span v-if="fee.docket_no">我方文号 {{ fee.docket_no }}</span>
            <span>{{ formatMoney(fee.amount_due, fee.currency) }}</span>
          </div>
        </div>
        <RouterLink
          to="/fees"
          class="button ghost"
          style="color:#fff;border-color:rgba(255,255,255,.4)"
        >
          ← 返回费用台账
        </RouterLink>
      </section>

      <section class="fee-layout">
        <article class="panel">
          <h2 class="section-heading">费用信息</h2>
          <div class="info-grid two-col">
            <div class="info-item"><label>费用类别</label><span>{{ feeLabels[fee.fee_type] ?? fee.fee_type }}</span></div>
            <div class="info-item"><label>状态</label><span>{{ feeStatusLabels[fee.status] ?? fee.status }}</span></div>
            <div class="info-item"><label>应付金额</label><span>{{ formatMoney(fee.amount_due, fee.currency) }}</span></div>
            <div class="info-item"><label>实付金额</label><span>{{ formatMoney(fee.amount_paid, fee.currency) }}</span></div>
            <div class="info-item"><label>官费应缴日</label><span>{{ formatDate(fee.due_date) }}</span></div>
            <div class="info-item"><label>缴纳日期</label><span>{{ formatDate(fee.paid_date) }}</span></div>
            <div class="info-item"><label>本次缴费缴至</label><span>{{ formatDate(fee.coverage_end_date) }}</span></div>
            <div class="info-item"><label>收款方</label><span>{{ fee.payee || '—' }}</span></div>
            <div class="info-item"><label>付款方</label><span>{{ fee.payer || '—' }}</span></div>
            <div class="info-item"><label>支付方式</label><span>{{ fee.payment_method || '—' }}</span></div>
            <div class="info-item full-row"><label>说明</label><span>{{ fee.description || '—' }}</span></div>
          </div>
          <p style="margin-top: 14px">
            <RouterLink v-if="fee.ip_asset_id" :to="`/assets/${fee.ip_asset_id}`" class="name-link">查看所属案件 →</RouterLink>
          </p>
        </article>

        <article class="panel">
          <h2 class="section-heading">关联发票</h2>
          <p v-if="invoices.length === 0" class="hint">
            该笔费用还没有发票。现实流程是先产生费用、后收发票，可点下方「登记发票」上传附件并自动识别。
          </p>
          <div v-for="invoice in invoices" :key="invoice.id" class="invoice-line">
            <div>
              <strong>{{ invoice.invoice_no }}</strong>
              <span v-if="invoice.invoice_code" class="hint"> · 代码 {{ invoice.invoice_code }}</span>
              <div class="hint">
                {{ formatDate(invoice.invoice_date) }} · {{ invoice.issuer || '开票单位未填' }}
              </div>
            </div>
            <div class="invoice-right">
              <span>{{ invoice.currency }} {{ invoice.amount_gross || '—' }}</span>
              <button
                v-if="invoice.file_material_id"
                class="button ghost small"
                @click="downloadAttachment(invoice)"
              >
                附件
              </button>
            </div>
          </div>

          <p v-if="invoices.length" class="hint" style="margin-top: 14px">
            发票合计 {{ centsToMoney(invoiceSumCents) }}，实付 {{ centsToMoney(paidAmountCents) }}，相差
            {{ centsToMoney(Math.abs(invoiceDiffCents)) }}
            <span v-if="invoiceDiffCents === 0">（一致）</span>
          </p>

          <div style="margin-top: 16px">
            <button class="button primary" @click="dialogOpen = true">＋ 登记发票</button>
          </div>
        </article>
      </section>

      <InvoiceDialog
        :open="dialogOpen"
        :asset-id="fee.ip_asset_id ?? ''"
        :fee-id="fee.id"
        @close="dialogOpen = false"
        @saved="onInvoiceSaved"
      />
    </template>
  </section>
</template>

<style scoped>
.fee-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}
.invoice-line {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #eef1f5;
  font-size: 13px;
}
.invoice-right {
  display: flex;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
}
@media (max-width: 1100px) {
  .fee-layout {
    grid-template-columns: 1fr;
  }
}
</style>
