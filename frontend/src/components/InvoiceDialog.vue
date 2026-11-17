<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, formatDate } from '../api'
import { centsToMoney, moneyToCents } from '../money'
import AssetPicker from './AssetPicker.vue'

interface AssetOption {
  id: string
  name: string
  docket_no?: string | null
}

interface FeeOption {
  id: string
  fee_type: string
  amount_due: string
  amount_paid: string | null
  due_date: string | null
  status: string
}

const props = withDefaults(
  defineProps<{
    open: boolean
    assetId?: string
    feeId?: string
  }>(),
  { assetId: '', feeId: '' },
)

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'saved', payload: { invoiceId: string; feeIds: string[] }): void
}>()

const assets = ref<AssetOption[]>([])
const caseFees = ref<FeeOption[]>([])
const loadingFees = ref(false)
const saving = ref(false)
const formError = ref('')
const editingCase = ref(false)

const attachmentId = ref('')
const attachmentName = ref('')
const previewUrl = ref('')
const recognizing = ref(false)
const recognizeNote = ref('')
const warnings = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const awaitingFile = ref<File | null>(null)
const zoom = ref(1)
const dialogEl = ref<HTMLElement | null>(null)
let triggerElement: HTMLElement | null = null
let extractionGeneration = 0

const feeLabels: Record<string, string> = {
  annuity: '年费',
  agency: '代理费',
  application: '申请费',
  substantive: '实审费',
  registration: '登记费',
  material: '材料费',
  other: '其他',
}

const statusLabels: Record<string, string> = {
  unpaid: '未支付',
  partial: '部分支付',
  paid: '已支付',
  canceled: '已取消',
}

const form = ref({
  ip_asset_id: '',
  invoice_no: '',
  invoice_code: '',
  issuer: '',
  invoice_date: '',
  amount_net: '',
  tax_amount: '',
  amount_gross: '',
  fee_ids: [] as string[],
})

const selectedCase = computed(() => assets.value.find((asset) => asset.id === form.value.ip_asset_id) ?? null)

const computedGrossCents = computed(() => moneyToCents(form.value.amount_net) + moneyToCents(form.value.tax_amount))
const grossDiffCents = computed(() => moneyToCents(form.value.amount_gross) - computedGrossCents.value)
const balanced = computed(() => grossDiffCents.value === 0 && moneyToCents(form.value.amount_gross) > 0)

const feeSumCents = computed(() =>
  caseFees.value
    .filter((fee) => form.value.fee_ids.includes(fee.id))
    .reduce((sum, fee) => sum + moneyToCents(fee.amount_paid || fee.amount_due), 0),
)

const feeDiffCents = computed(() => moneyToCents(form.value.amount_gross) - feeSumCents.value)

function releasePreview() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

async function loadAssets() {
  try {
    const page = await api.assets({ page: 1, page_size: 20 })
    assets.value = page.items as unknown as AssetOption[]
  } catch {
    assets.value = []
  }
}

async function searchAssets(query: string): Promise<AssetOption[]> {
  const page = await api.assets({ q: query, page: 1, page_size: 20 })
  return page.items.map((item) => ({
    id: item.id,
    name: item.name,
    docket_no: item.docket_no,
  }))
}

async function loadCaseFees(assetId: string) {
  caseFees.value = []
  if (!assetId) return
  loadingFees.value = true
  try {
    const result = await api.fees({ ip_asset_id: assetId, page: 1, page_size: 100 })
    caseFees.value = result.items as unknown as FeeOption[]
  } catch {
    caseFees.value = []
  } finally {
    loadingFees.value = false
  }
}

async function reset() {
  extractionGeneration += 1
  recognizing.value = false
  formError.value = ''
  form.value = {
    ip_asset_id: props.assetId || '',
    invoice_no: '',
    invoice_code: '',
    issuer: '',
    invoice_date: '',
    amount_net: '',
    tax_amount: '',
    amount_gross: '',
    fee_ids: props.feeId ? [props.feeId] : [],
  }
  attachmentId.value = ''
  attachmentName.value = ''
  recognizeNote.value = ''
  warnings.value = []
  editingCase.value = false
  zoom.value = 1
  releasePreview()
  if (fileInput.value) fileInput.value.value = ''
  if (!assets.value.length) await loadAssets()
  if (form.value.ip_asset_id) await loadCaseFees(form.value.ip_asset_id)
}

onMounted(() => {
  if (props.open) void reset()
})

// 组件常驻，每次打开都要按新的案件/费用重新初始化
watch(
  () => props.open,
  (value) => {
    if (value) {
      triggerElement = document.activeElement as HTMLElement | null
      void reset().then(() => nextTick(() => dialogEl.value?.focus()))
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
      triggerElement?.focus()
    }
  },
)

onBeforeUnmount(() => {
  extractionGeneration += 1
  releasePreview()
  document.body.style.overflow = ''
})

defineExpose({ reset })

function close() {
  extractionGeneration += 1
  recognizing.value = false
  releasePreview()
  emit('close')
}

function onCaseChange(value: string) {
  form.value.ip_asset_id = value
  form.value.fee_ids = []
  editingCase.value = false
  void loadCaseFees(value)
}

function toggleFee(feeId: string) {
  const list = form.value.fee_ids
  form.value.fee_ids = list.includes(feeId) ? list.filter((item) => item !== feeId) : [...list, feeId]
}

function toggleZoom(delta: number) {
  zoom.value = Math.min(2.5, Math.max(0.6, Number((zoom.value + delta).toFixed(2))))
}

function openOriginal() {
  if (previewUrl.value) window.open(previewUrl.value, '_blank')
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  awaitingFile.value = file
  await recognizeFile(file)
}

async function recognizeFile(file: File) {
  const generation = ++extractionGeneration
  attachmentName.value = file.name
  recognizing.value = true
  recognizeNote.value = ''
  warnings.value = []
  try {
    const result = await api.recognizeInvoice(file, form.value.ip_asset_id || undefined)
    if (generation !== extractionGeneration) return
    attachmentId.value = result.material_id
    recognizeNote.value = '附件已保存，后台识别中…'
    releasePreview()
    try {
      previewUrl.value = await api.previewMaterialUrl(result.material_id)
    } catch {
      /* 预览失败不影响识别 */
    }

    await pollExtraction(result.material_id, generation)
  } catch (err) {
    if (generation === extractionGeneration) recognizeNote.value = err instanceof Error ? err.message : '识别失败，可手工填写；附件已保留'
  } finally {
    if (generation === extractionGeneration) recognizing.value = false
  }
}

async function pollExtraction(materialId: string, generation = extractionGeneration) {
  let extraction = await api.extractionResult(materialId)
  if (generation !== extractionGeneration) return
  const deadline = Date.now() + 120_000
  while (['pending', 'running'].includes(extraction.status) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1200))
    extraction = await api.extractionResult(materialId)
    if (generation !== extractionGeneration) return
  }
  if (generation !== extractionGeneration) return
  if (extraction.status === 'failed') {
    throw new Error(extraction.error || '识别失败，附件已保留，可重新识别')
  }
  if (extraction.status !== 'succeeded') {
    throw new Error('识别仍在后台运行，附件已保留，请稍后重新识别')
  }
  const fields = extraction.fields
  if (fields.invoice_no) form.value.invoice_no = fields.invoice_no
  if (fields.invoice_code) form.value.invoice_code = fields.invoice_code
  if (fields.invoice_date) form.value.invoice_date = fields.invoice_date
  if (fields.amount_net) form.value.amount_net = fields.amount_net
  if (fields.tax_amount) form.value.tax_amount = fields.tax_amount
  if (fields.amount_gross) form.value.amount_gross = fields.amount_gross
  if (fields.seller) form.value.issuer = fields.seller
  warnings.value = extraction.warnings
  recognizeNote.value = extraction.warnings.length
    ? '识别完成，请核对提示项'
    : `识别完成（${extraction.source === 'ocr' ? 'OCR' : 'PDF 文本层'}）`
}

async function reRecognize() {
  if (!attachmentId.value) {
    fileInput.value?.click()
    return
  }
  const generation = ++extractionGeneration
  recognizing.value = true
  recognizeNote.value = '使用现有附件重新识别中…'
  warnings.value = []
  try {
    await api.retryInvoiceExtraction(attachmentId.value)
    if (generation !== extractionGeneration) return
    await pollExtraction(attachmentId.value, generation)
  } catch (err) {
    if (generation === extractionGeneration) recognizeNote.value = err instanceof Error ? err.message : '重新识别失败，附件仍已保留'
  } finally {
    if (generation === extractionGeneration) recognizing.value = false
  }
}

async function downloadAttachment(materialId: string, filename: string) {
  try {
    await api.downloadMaterialFile(materialId, filename)
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '附件下载失败'
  }
}

async function save() {
  formError.value = ''
  if (!form.value.ip_asset_id) {
    formError.value = '请选择发票所属案件'
    return
  }
  if (!form.value.invoice_no.trim()) {
    formError.value = '发票号码必填'
    return
  }
  saving.value = true
  try {
    const created = await api.createInvoice({
      ip_asset_id: form.value.ip_asset_id,
      invoice_no: form.value.invoice_no.trim(),
      invoice_code: form.value.invoice_code.trim() || null,
      issuer: form.value.issuer || null,
      invoice_date: form.value.invoice_date || null,
      amount_net: form.value.amount_net || null,
      tax_amount: form.value.tax_amount || null,
      amount_gross: form.value.amount_gross || null,
      currency: 'CNY',
      fee_ids: form.value.fee_ids,
      file_material_id: attachmentId.value || null,
    })
    releasePreview()
    emit('saved', {
      invoiceId: String(created.id ?? ''),
      feeIds: [...form.value.fee_ids],
    })
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="open" class="inv-mask" @click.self="close" @keydown.esc="close">
    <section ref="dialogEl" class="inv-modal" role="dialog" aria-modal="true" aria-label="登记发票" tabindex="-1" :aria-busy="recognizing || saving">
      <header class="inv-head">
        <div>
          <h2>登记发票</h2>
          <div class="inv-meta" role="status" aria-live="polite">
            <span v-if="attachmentId" class="badge green">附件已保存：{{ attachmentName }}</span>
            <span v-else class="badge">尚未上传附件</span>
            <span v-if="recognizing" class="badge amber">识别中…</span>
            <span v-else-if="recognizeNote" class="badge">{{ recognizeNote }}</span>
            <span v-if="warnings.length" class="badge amber">{{ warnings.length }} 项需人工核对</span>
          </div>
        </div>
        <button class="icon-button" aria-label="关闭" @click="close">×</button>
      </header>

      <div class="inv-body">
        <aside class="inv-preview">
          <div class="inv-bar">
            <button class="inv-icon" title="缩小" @click="toggleZoom(-0.2)">−</button>
            <span>{{ Math.round(zoom * 100) }}%</span>
            <button class="inv-icon" title="放大" @click="toggleZoom(0.2)">+</button>
            <span style="flex: 1"></span>
            <input ref="fileInput" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" style="display: none" @change="onFileChange" />
            <button class="button small" :disabled="recognizing" @click="reRecognize">
              {{ attachmentId ? '重新识别' : '上传发票' }}
            </button>
            <button class="inv-icon" title="在新标签打开" @click="openOriginal">⤢</button>
          </div>
          <div class="inv-sheet-wrap">
            <img v-if="previewUrl" :src="previewUrl" class="inv-sheet" :style="{ width: `${zoom * 100}%` }" alt="发票预览" />
            <div v-else class="inv-placeholder">
              <p>还没有发票附件</p>
              <p class="hint">点击上方「上传发票」，支持 PDF 或图片</p>
              <button class="button primary small" @click="fileInput?.click()">选择文件</button>
            </div>
          </div>
          <details v-if="warnings.length" class="inv-warn-list">
            <summary>需要人工核对 {{ warnings.length }} 项</summary>
            <ul>
              <li v-for="warning in warnings" :key="warning">{{ warning }}</li>
            </ul>
          </details>
        </aside>

        <div class="inv-form">
          <div class="inv-scroll">
            <div class="inv-section">
              <h4>归属案件<span class="line"></span></h4>
              <AssetPicker
                v-if="editingCase || !selectedCase"
                v-model="form.ip_asset_id"
                :assets="assets"
                :search="searchAssets"
                placeholder="输入案件名称或我方文号搜索（必选）"
                @update:model-value="onCaseChange"
              />
              <div v-else class="inv-case">
                <span>{{ selectedCase.name }}</span>
                <span class="hint">{{ selectedCase.docket_no }}</span>
                <span style="flex: 1"></span>
                <button class="link-button" @click="editingCase = true">更换</button>
              </div>
              <p class="hint" style="margin: 6px 0 0">发票归属案件后，可在费用台账中按案件查看与对账。</p>
            </div>

            <div class="inv-section">
              <h4>票面信息<span class="line"></span></h4>
              <div class="inv-grid2">
                <div class="form-item">
                  <label for="inv_no">发票号码 *</label>
                  <input id="inv_no" v-model="form.invoice_no" placeholder="识别后自动填入" />
                </div>
                <div class="form-item">
                  <label for="inv_code">发票代码</label>
                  <input id="inv_code" v-model="form.invoice_code" placeholder="选填" />
                </div>
                <div class="form-item">
                  <label for="inv_date">开票日期</label>
                  <input id="inv_date" v-model="form.invoice_date" type="date" />
                </div>
                <div class="form-item">
                  <label for="inv_issuer">开票单位</label>
                  <input id="inv_issuer" v-model="form.issuer" placeholder="识别为销售方名称" />
                </div>
              </div>
            </div>

            <div class="inv-section">
              <h4>
                金额<span class="line"></span>
                <span class="badge" :class="balanced ? 'green' : 'amber'">{{ balanced ? '勾稽一致' : '待核对' }}</span>
              </h4>
              <div class="inv-grid3">
                <div class="form-item">
                  <label for="inv_net">不含税金额</label>
                  <input id="inv_net" v-model="form.amount_net" inputmode="decimal" />
                </div>
                <div class="form-item">
                  <label for="inv_tax">税额</label>
                  <input id="inv_tax" v-model="form.tax_amount" inputmode="decimal" />
                </div>
                <div class="form-item">
                  <label for="inv_gross">价税合计</label>
                  <input id="inv_gross" v-model="form.amount_gross" inputmode="decimal" />
                </div>
              </div>
              <p class="hint" style="margin: 8px 0 0">
                不含税 + 税额 = {{ centsToMoney(computedGrossCents) }}；与价税合计相差 {{ centsToMoney(Math.abs(grossDiffCents)) }}
              </p>
            </div>

            <div class="inv-section">
              <h4>关联费用<span class="line"></span></h4>
              <p v-if="!form.ip_asset_id" class="hint">请先选择案件</p>
              <p v-else-if="loadingFees" class="hint">加载中…</p>
              <p v-else-if="caseFees.length === 0" class="hint">该案件还没有费用记录，可先在费用台账登记</p>
              <div v-else class="inv-fee-list">
                <label v-for="fee in caseFees" :key="fee.id" class="inv-fee-row">
                  <input type="checkbox" :checked="form.fee_ids.includes(fee.id)" @change="toggleFee(fee.id)" />
                  <span>{{ feeLabels[fee.fee_type] ?? fee.fee_type }}</span>
                  <span class="hint">{{ formatDate(fee.due_date) }} · {{ statusLabels[fee.status] ?? fee.status }}</span>
                  <span class="inv-amount">{{ fee.amount_paid || fee.amount_due }}</span>
                </label>
                <div class="inv-fee-foot">
                  <span>已选 {{ form.fee_ids.length }} 笔</span>
                  <span>小计 ¥{{ centsToMoney(feeSumCents) }}</span>
                </div>
              </div>
              <p v-if="form.fee_ids.length && feeDiffCents !== 0" class="hint" style="margin: 8px 0 0">
                费用小计 {{ centsToMoney(feeSumCents) }} 与发票价税合计 {{ centsToMoney(moneyToCents(form.amount_gross)) }} 相差
                {{ centsToMoney(Math.abs(feeDiffCents)) }}，请确认。
              </p>
            </div>

            <div class="inv-section">
              <h4>附件<span class="line"></span></h4>
              <div v-if="attachmentId" class="inv-attach">
                <span>📄 {{ attachmentName }}</span>
                <span style="flex: 1"></span>
                <button class="button ghost small" @click="downloadAttachment(attachmentId, attachmentName)">下载</button>
                <button class="button ghost small" @click="fileInput?.click()">替换</button>
              </div>
              <div v-else class="inv-attach empty">
                <span class="hint">未上传附件；上传后可自动识别票面并保存原件</span>
                <span style="flex: 1"></span>
                <button class="button ghost small" @click="fileInput?.click()">上传</button>
              </div>
            </div>
          </div>

          <footer class="inv-foot">
            <span class="hint">
              将保存 <strong>{{ form.invoice_no ? 1 : 0 }}</strong> 张发票，关联 <strong>{{ form.fee_ids.length }}</strong> 笔费用，合计
              <strong>¥{{ centsToMoney(feeSumCents) }}</strong>
            </span>
            <span style="flex: 1"></span>
            <span v-if="formError" class="error-text" style="margin-right: 10px">{{ formError }}</span>
            <button class="button ghost" @click="close">取消</button>
            <button class="button primary" :disabled="saving || !form.ip_asset_id" @click="save">
              {{ saving ? '保存中…' : '保存发票' }}
            </button>
          </footer>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.inv-mask {
  position: fixed;
  inset: 0;
  background: rgba(7, 18, 38, 0.55);
  z-index: 220;
  display: grid;
  place-items: center;
  padding: 20px;
}
.inv-modal {
  width: 1200px;
  max-width: 100%;
  height: 88vh;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.inv-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
}
.inv-head h2 {
  font-size: 17px;
  margin: 0 0 6px;
}
.inv-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--muted);
  flex-wrap: wrap;
}
.inv-body {
  display: grid;
  grid-template-columns: 430px 1fr;
  flex: 1;
  min-height: 0;
}
.inv-preview {
  border-right: 1px solid var(--line);
  background: #eef2f7;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.inv-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  background: #fff;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
  color: var(--muted);
}
.inv-icon {
  width: 26px;
  height: 26px;
  border: 1px solid var(--line);
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  color: #475269;
}
.inv-sheet-wrap {
  flex: 1;
  overflow: auto;
  padding: 14px;
  display: grid;
  place-items: start center;
}
.inv-sheet {
  display: block;
  max-width: 100%;
  height: auto;
  background: #fff;
  box-shadow: 0 6px 24px rgba(25, 45, 76, 0.16);
}
.inv-placeholder {
  text-align: center;
  padding: 40px 16px;
  color: var(--muted);
  font-size: 13px;
}
.inv-warn-list {
  border-top: 1px solid var(--line);
  background: #fff;
  font-size: 12px;
}
.inv-warn-list summary {
  padding: 9px 12px;
  color: #b97511;
  cursor: pointer;
}
.inv-warn-list ul {
  margin: 0;
  padding: 0 24px 12px;
  color: var(--muted);
}
.inv-form {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.inv-scroll {
  flex: 1;
  overflow: auto;
  padding: 14px 20px 0;
}
.inv-section {
  margin-bottom: 16px;
}
.inv-section h4 {
  margin: 0 0 10px;
  font-size: 13px;
  color: #475269;
  display: flex;
  align-items: center;
  gap: 8px;
}
.inv-section h4 .line {
  flex: 1;
  height: 1px;
  background: var(--line);
}
.inv-case {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  background: #fbfcfe;
  font-size: 13px;
}
.inv-grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.inv-grid3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.inv-fee-list {
  border: 1px solid var(--line);
  border-radius: 9px;
  overflow: hidden;
}
.inv-fee-row {
  display: grid;
  grid-template-columns: 24px 90px 1fr 110px;
  gap: 10px;
  align-items: center;
  padding: 9px 12px;
  border-bottom: 1px solid #f0f2f6;
  font-size: 12px;
  cursor: pointer;
}
.inv-fee-row:hover {
  background: #f8fbff;
}
.inv-amount {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.inv-fee-foot {
  display: flex;
  justify-content: space-between;
  padding: 9px 12px;
  background: #fbfcfe;
  font-size: 12px;
  color: var(--muted);
}
.inv-attach {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px dashed #9eb7df;
  background: #f8fbff;
  border-radius: 9px;
  padding: 10px 12px;
  font-size: 12px;
}
.inv-attach.empty {
  border-color: var(--line);
  background: #fbfcfe;
}
.inv-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 20px;
  border-top: 1px solid var(--line);
  background: #fff;
  font-size: 12px;
}
</style>
