<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { materialCategoryLabels as categoryLabels, materialFlagLabels as flagLabels } from '../labels'
import { useToast } from '../toast'
import AssetPicker from '../components/AssetPicker.vue'
import { useAuth } from '../auth'

const route = useRoute()
const { canWrite } = useAuth()
const toast = useToast()
const assetFilter = ref(String(route.query.asset || ''))
const assetLabel = ref('')

interface MaterialRow {
  id: string
  display_name: string
  original_name: string
  category: string
  ext?: string | null
  mime_type?: string | null
  version: string | null
  size_bytes: number
  flag: string
  created_at: string
  ip_asset_id?: string | null
  asset_name?: string | null
  docket_no?: string | null
  remark?: string | null
}

interface AssetOption {
  id: string
  name: string
  docket_no?: string | null
}

type FieldTarget = 'name' | 'patent' | 'party' | 'none'
type FieldState = 'new' | 'overwrite' | 'same' | 'none' | 'readonly'

interface FieldRow {
  key: string
  label: string
  current: string
  value: string
  target: FieldTarget
  state: FieldState
  checked: boolean
  readonly: boolean
}

const items = ref<MaterialRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const assets = ref<AssetOption[]>([])
const loading = ref(true)
const error = ref('')
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const uploadOpen = ref(false)
const uploadDrawer = ref<HTMLElement | null>(null)
const uploadError = ref('')
const category = ref('certificate_scan')
const assetId = ref('')
const remark = ref('')
const keyword = ref('')

const editing = ref(false)
const editItem = ref<MaterialRow | null>(null)
const editRemark = ref('')
const editFile = ref<File | null>(null)
const editFileInput = ref<HTMLInputElement | null>(null)
const editDrawer = ref<HTMLElement | null>(null)
const editError = ref('')
const editSaving = ref(false)

const recognizingId = ref('')
const reviewing = ref(false)
const reviewPhase = ref<'loading' | 'ready' | 'error'>('loading')
const reviewError = ref('')
const reviewItem = ref<MaterialRow | null>(null)
const applying = ref(false)
const applied = ref(false)
const applyMessage = ref('')
const reviewAssetName = ref('')
const reviewAssetId = ref('')
const reviewMaterialId = ref('')
const reviewSource = ref('')
const reviewWarnings = ref<string[]>([])
const reviewText = ref('')
const previewUrl = ref('')
const previewError = ref('')
const zoom = ref(1)
const rows = ref<FieldRow[]>([])
const partyExisting = ref<string>('')

const viewing = ref(false)
const viewItem = ref<MaterialRow | null>(null)
const viewKind = ref<'pdf' | 'image' | 'other'>('other')
const viewPage = ref(0)
const viewPageCount = ref(1)
const viewZoom = ref(1)
const viewLoading = ref(false)
const viewError = ref('')
const viewUrl = ref('')
let reviewSeq = 0
let viewSeq = 0

async function searchAssets(query: string): Promise<AssetOption[]> {
  const page = await api.assets({ q: query, page: 1, page_size: 20 })
  return page.items.map((item) => ({ id: item.id, name: item.name, docket_no: item.docket_no }))
}

const fileTypeLabels: Record<string, string> = {
  pdf: 'PDF',
  image: '图片',
  word: 'Word',
  excel: 'Excel',
  zip: 'ZIP',
  other: '其他',
}

function fileExt(item: { ext?: string | null; original_name?: string }): string {
  const ext = (item.ext || '').trim().toLowerCase()
  if (ext) return ext.replace(/^\./, '')
  const name = item.original_name || ''
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : ''
}

function fileTypeKey(item: { ext?: string | null; original_name?: string }): string {
  const ext = fileExt(item)
  if (ext === 'pdf') return 'pdf'
  if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) return 'image'
  if (['doc', 'docx'].includes(ext)) return 'word'
  if (['xls', 'xlsx'].includes(ext)) return 'excel'
  if (ext === 'zip') return 'zip'
  return 'other'
}

function fileTypeLabel(item: { ext?: string | null; original_name?: string }): string {
  return fileTypeLabels[fileTypeKey(item)] ?? '其他'
}

function canRecognize(item: { ext?: string | null; original_name?: string }): boolean {
  return ['pdf', 'image'].includes(fileTypeKey(item))
}

function selectedFileTypeLabel(): string {
  return selectedFile.value ? fileTypeLabel({ original_name: selectedFile.value.name }) : '选择文件后自动识别'
}

const stateLabels: Record<FieldState, string> = {
  new: '新增',
  overwrite: '将覆盖',
  same: '一致',
  none: '未识别',
  readonly: '仅展示',
}

const checkedRows = computed(() => rows.value.filter((row) => !row.readonly && row.checked && row.value.trim()))
const summaryText = computed(() => {
  const total = rows.value.filter((row) => !row.readonly).length
  return `将写入 ${checkedRows.value.length} 项，跳过 ${total - checkedRows.value.length} 项`
})

function fieldState(current: string, value: string): FieldState {
  const c = current.trim()
  const v = value.trim()
  if (!v) return 'none'
  if (!c) return 'new'
  if (c === v) return 'same'
  return 'overwrite'
}

/** 手工修改识别值后立即重算状态：新输入的内容默认勾选写入，清空后不可写入。 */
function onValueInput(row: FieldRow, event: Event) {
  if (row.readonly) return
  row.value = (event.target as HTMLInputElement).value
  row.state = fieldState(row.current, row.value)
  row.checked = row.state === 'new' || row.state === 'overwrite'
  // 已写入后又改出了新的「新增 / 将覆盖」内容时，恢复「写入档案」按钮，允许再次提交这次修改。
  if (row.checked && applied.value) {
    applied.value = false
    applyMessage.value = ''
  }
}

function push(kind: 'field' | 'readonly', key: string, label: string, current: string, value: string, target: FieldTarget) {
  const state = kind === 'readonly' ? 'readonly' : fieldState(current, value)
  rows.value.push({
    key,
    label,
    current,
    value,
    target,
    state,
    checked: state === 'new' || state === 'overwrite',
    readonly: kind === 'readonly',
  })
}

async function load() {
  loading.value = true
  try {
    const [result, assetPage] = await Promise.all([
      api.materials({
        q: keyword.value.trim() || undefined,
        page: page.value,
        page_size: pageSize,
        ...(assetFilter.value ? { ip_asset_id: assetFilter.value } : {}),
      }),
      api.assets({ page: 1, page_size: 20 }),
    ])
    items.value = result.items as unknown as MaterialRow[]
    total.value = result.total
    assets.value = assetPage.items as unknown as AssetOption[]
    if (assetFilter.value) {
      const target = assetPage.items.find((item) => item.id === assetFilter.value)
      assetLabel.value = target ? target.name : ''
    }
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

function clearFilter() {
  assetFilter.value = ''
  assetLabel.value = ''
  keyword.value = ''
  page.value = 1
  void load()
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
  uploadError.value = ''
}

function clearSelectedFile() {
  selectedFile.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function openUpload() {
  selectedFile.value = null
  if (fileInput.value) fileInput.value.value = ''
  remark.value = ''
  assetId.value = assetFilter.value
  category.value = 'certificate_scan'
  uploadError.value = ''
  uploadOpen.value = true
  void nextTick(() => uploadDrawer.value?.focus())
}

function closeUpload() {
  if (uploading.value) return
  uploadOpen.value = false
}

async function upload() {
  const file = selectedFile.value
  if (!file) {
    uploadError.value = '请选择文件'
    return
  }
  if (!assetId.value) {
    uploadError.value = '请先选择关联案件'
    return
  }
  uploading.value = true
  uploadError.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('category', category.value)
    form.append('ip_asset_id', assetId.value)
    if (remark.value.trim()) form.append('remark', remark.value.trim())
    await api.uploadMaterial(form)
    clearSelectedFile()
    remark.value = ''
    uploadOpen.value = false
    toast.success(`已上传「${file.name}」`)
    await load()
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    uploading.value = false
  }
}

function openEdit(item: MaterialRow) {
  editItem.value = item
  editRemark.value = item.remark ?? ''
  editFile.value = null
  if (editFileInput.value) editFileInput.value.value = ''
  editError.value = ''
  editing.value = true
  void nextTick(() => editDrawer.value?.focus())
}

function closeEdit() {
  if (editSaving.value) return
  editing.value = false
  editItem.value = null
}

function onEditFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  editFile.value = target.files?.[0] ?? null
  editError.value = ''
}

function clearEditFile() {
  editFile.value = null
  if (editFileInput.value) editFileInput.value.value = ''
}

async function saveEdit() {
  if (!editItem.value) return
  editSaving.value = true
  editError.value = ''
  try {
    if (editFile.value) {
      const form = new FormData()
      form.append('file', editFile.value)
      form.append('remark', editRemark.value.trim())
      await api.replaceMaterialFile(editItem.value.id, form)
      toast.success(`已更换「${editItem.value.display_name}」的文件`)
    } else {
      await api.updateMaterial(editItem.value.id, { remark: editRemark.value.trim() || null })
      toast.success(`已更新「${editItem.value.display_name}」的备注`)
    }
    editing.value = false
    editItem.value = null
    await load()
  } catch (err) {
    editError.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    editSaving.value = false
  }
}

async function remove(id: string) {
  if (!confirm('确认逻辑删除该材料？文件保留在存储层，可由管理员恢复。')) return
  try {
    await api.deleteMaterial(id)
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败'
  }
}

async function download(id: string) {
  try {
    const item = items.value.find((row) => row.id === id)
    await api.downloadMaterialFile(id, item?.original_name ?? 'material')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '下载失败'
  }
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function releasePreview() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

function releaseViewUrl() {
  if (viewUrl.value) {
    URL.revokeObjectURL(viewUrl.value)
    viewUrl.value = ''
  }
}

function closeReview() {
  reviewSeq++
  releasePreview()
  reviewing.value = false
  recognizingId.value = ''
  reviewItem.value = null
  reviewPhase.value = 'loading'
  reviewError.value = ''
  rows.value = []
  reviewText.value = ''
  applied.value = false
}

function viewerKind(item: MaterialRow): 'pdf' | 'image' | 'other' {
  const ext = (item.ext || item.original_name.split('.').pop() || '').toLowerCase()
  if (ext === 'pdf') return 'pdf'
  if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) return 'image'
  return 'other'
}

async function loadViewerPage(item: MaterialRow, page: number) {
  const seq = ++viewSeq
  viewPage.value = page
  viewLoading.value = true
  viewError.value = ''
  releaseViewUrl()
  try {
    const { url, pageCount } = await api.previewMaterialPage(item.id, page)
    if (seq !== viewSeq) {
      URL.revokeObjectURL(url)
      return
    }
    viewUrl.value = url
    viewPageCount.value = pageCount
  } catch (err) {
    if (seq === viewSeq) viewError.value = err instanceof Error ? err.message : '原件预览加载失败'
  } finally {
    if (seq === viewSeq) viewLoading.value = false
  }
}

function openViewer(item: MaterialRow) {
  viewItem.value = item
  viewKind.value = viewerKind(item)
  viewError.value = ''
  viewPage.value = 0
  viewPageCount.value = 1
  viewZoom.value = 1
  viewing.value = true
  releaseViewUrl()
  if (viewKind.value === 'other') {
    viewLoading.value = false
    return
  }
  void loadViewerPage(item, 0)
}

function changeViewPage(delta: number) {
  if (!viewItem.value) return
  const next = viewPage.value + delta
  if (next < 0 || next >= viewPageCount.value) return
  void loadViewerPage(viewItem.value, next)
}

function toggleViewZoom(delta: number) {
  viewZoom.value = Math.min(2.5, Math.max(0.6, Number((viewZoom.value + delta).toFixed(2))))
}

function closeViewer() {
  viewSeq++
  releaseViewUrl()
  viewing.value = false
  viewItem.value = null
  viewError.value = ''
  viewLoading.value = false
  viewPage.value = 0
  viewPageCount.value = 1
  viewZoom.value = 1
}

function downloadViewed() {
  if (viewItem.value) void download(viewItem.value.id)
}

async function loadReviewPreview(item: MaterialRow, seq: number) {
  previewError.value = ''
  try {
    const url = await api.previewMaterialUrl(item.id)
    if (seq !== reviewSeq) {
      URL.revokeObjectURL(url)
      return
    }
    previewUrl.value = url
  } catch (err) {
    if (seq === reviewSeq) previewError.value = err instanceof Error ? err.message : '预览加载失败'
  }
}

/** 点击识别立即打开确认框，预览与识别并行加载。 */
async function recognize(item: MaterialRow) {
  if (!canRecognize(item)) {
    error.value = '该文件类型不支持识别，仅支持 PDF 和图片'
    return
  }
  if (!item.ip_asset_id) {
    error.value = '该材料未关联案件，请先关联后再识别'
    return
  }
  const assetId = item.ip_asset_id
  const seq = ++reviewSeq
  error.value = ''
  reviewing.value = true
  recognizingId.value = item.id
  reviewPhase.value = 'loading'
  reviewError.value = ''
  reviewItem.value = item
  reviewAssetId.value = assetId
  reviewAssetName.value = item.asset_name || '正在加载案件…'
  reviewMaterialId.value = item.id
  reviewSource.value = ''
  reviewWarnings.value = []
  reviewText.value = ''
  partyExisting.value = ''
  applyMessage.value = ''
  applied.value = false
  zoom.value = 1
  rows.value = []
  releasePreview()
  void loadReviewPreview(item, seq)

  try {
    const [, detail] = await Promise.all([
      api.extractMaterial(item.id),
      api.asset(assetId),
    ])
    if (seq !== reviewSeq) return
    reviewAssetName.value = detail.name
    let result = await api.extractionResult(item.id)
    const deadline = Date.now() + 120_000
    while (['pending', 'running'].includes(result.status) && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 1200))
      if (seq !== reviewSeq) return
      result = await api.extractionResult(item.id)
    }
    if (seq !== reviewSeq) return
    if (result.status === 'failed') {
      throw new Error(result.error || '识别失败，原始附件已保留，可重试')
    }
    if (result.status !== 'succeeded') {
      throw new Error('识别仍在后台运行，请稍后重试')
    }
    const fields = result.fields
    const patent = (detail.patent ?? {}) as Record<string, string | null>
    const currentParty = (detail.parties || [])[0]?.name ?? ''

    reviewSource.value = result.source || 'ocr'
    reviewWarnings.value = result.warnings
    reviewText.value = result.text
    partyExisting.value = currentParty
    rows.value = []

    push('field', 'name', '案件名称', detail.name, fields.name ?? '', 'name')
    push('field', 'patent_no', '专利号', patent.patent_no ?? '', fields.patent_no ?? '', 'patent')
    push('field', 'application_no', '申请号', patent.application_no ?? '', fields.application_no ?? '', 'patent')
    push('field', 'application_date', '申请日', patent.application_date ?? '', fields.application_date ?? '', 'patent')
    push('field', 'grant_date', '授权公告日', patent.grant_date ?? '', fields.grant_date ?? '', 'patent')
    push('field', 'legal_status', '法律状态', patent.legal_status ?? '', fields.legal_status ?? '', 'patent')
    push('field', 'patentee', '专利权人', currentParty, fields.patentee ?? '', 'party')
    push('readonly', 'certificate_no', '证书号', '—', fields.certificate_no ?? '', 'none')
    push('readonly', 'inventors', '发明人', '—', fields.inventors ?? '', 'none')

    reviewPhase.value = 'ready'
  } catch (err) {
    if (seq === reviewSeq) {
      reviewError.value = err instanceof Error ? err.message : '识别失败'
      reviewPhase.value = 'error'
    }
  } finally {
    if (seq === reviewSeq) recognizingId.value = ''
  }
}

function retryRecognition() {
  if (reviewItem.value) void recognize(reviewItem.value)
}

function setBulk(mode: 'all' | 'none' | 'empty') {
  rows.value.forEach((row) => {
    if (row.readonly) return
    if (mode === 'all') row.checked = true
    else if (mode === 'none') row.checked = false
    else row.checked = row.state === 'new' || row.state === 'overwrite'
  })
}

function toggleZoom(delta: number) {
  zoom.value = Math.min(2.5, Math.max(0.6, Number((zoom.value + delta).toFixed(2))))
}

async function openOriginal() {
  if (!previewUrl.value) return
  window.open(previewUrl.value, '_blank')
}

async function applyReview() {
  if (applying.value || applied.value) return
  if (checkedRows.value.length === 0) {
    applyMessage.value = '没有勾选任何字段'
    return
  }
  const targets = checkedRows.value
  applying.value = true
  applyMessage.value = ''
  try {
    const detail = await api.asset(reviewAssetId.value)
    const currentPatent = (detail.patent as Record<string, unknown> | null) ?? {}
    const patent: Record<string, unknown> = { patent_type: currentPatent.patent_type ?? 'invention' }
    const payload: Record<string, unknown> = {}
    let partyName = ''
    let hasPatentFields = false

    for (const row of targets) {
      if (row.target === 'patent') {
        patent[row.key] = row.value.trim()
        hasPatentFields = true
      } else if (row.target === 'name') payload.name = row.value.trim()
      else if (row.target === 'party') partyName = row.value.trim()
    }
    // 只在确实勾选了专利字段时提交专业字段，避免给软著 / 商标档案带上跨类型字段而返回 422。
    if (hasPatentFields) payload.patent = patent

    if (partyName) {
      const existing = await api.parties({ q: partyName, page: 1, page_size: 20 })
      const hit = (existing.items as Array<{ id: string; name: string }>).find((party) => party.name === partyName)
      const partyId = hit ? hit.id : (await api.createParty({ name: partyName })).id
      const relations = (detail.parties || []).map((party, index) => ({
        party_id: party.id,
        role: 'patentee',
        seq: index,
      }))
      if (!relations.some((item) => item.party_id === partyId)) {
        relations.push({ party_id: partyId, role: 'patentee', seq: relations.length })
      }
      payload.parties = relations
    }

    await api.updateAsset(reviewAssetId.value, payload)
    for (const row of targets) {
      row.current = row.value.trim()
      row.checked = false
      row.state = fieldState(row.current, row.value)
    }
    applied.value = true
    applyMessage.value = `已写入 ${targets.length} 项，可在档案详情中核对；本次识别结果不能重复写入`
    await load()
  } catch (err) {
    applyMessage.value = err instanceof Error ? err.message : '写入失败'
  } finally {
    applying.value = false
  }
}

onMounted(async () => {
  await load()
  if (route.query.upload === '1') {
    openUpload()
  }
})
onBeforeUnmount(releasePreview)
</script>

<template>
  <section>
    <div class="page-head">
      <div>
        <h1>材料中心</h1>
        <p>按案件名称关联材料；证书扫描件可识别后确认写入档案</p>
      </div>
    </div>

    <div class="toolbar">
      <button v-if="canWrite" class="button primary" @click="openUpload">上传资料</button>
      <input
        v-model="keyword"
        class="field"
        placeholder="搜索文件名称"
        style="width: 260px"
        @keyup.enter="query"
      />
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
            <th>文件名称</th>
            <th>类型</th>
            <th>分类</th>
            <th>大小</th>
            <th>标识</th>
            <th>备注</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td style="min-width: 220px">
              <RouterLink v-if="item.ip_asset_id" :to="`/assets/${item.ip_asset_id}`" class="name-link">
                {{ item.asset_name || '未命名案件' }}
              </RouterLink>
              <span v-else class="hint">未关联案件</span>
            </td>
            <td>{{ item.display_name }}</td>
            <td><span class="badge gray">{{ fileTypeLabel(item) }}</span></td>
            <td>{{ categoryLabels[item.category] ?? item.category }}</td>
            <td>{{ humanSize(item.size_bytes) }}</td>
            <td><span class="badge">{{ flagLabels[item.flag] ?? item.flag }}</span></td>
            <td style="max-width: 260px">{{ item.remark || '—' }}</td>
            <td>
              <div class="row-actions">
                <button class="button ghost small" @click="openViewer(item)">查看</button>
                <button v-if="canWrite" class="button ghost small" @click="openEdit(item)">修改</button>
                <button v-if="canWrite && canRecognize(item)" class="button ghost small" :disabled="!!recognizingId" @click="recognize(item)">
                  <span v-if="recognizingId === item.id" class="spinner small" aria-hidden="true"></span>{{ recognizingId === item.id ? '识别中…' : '识别' }}
                </button>
                <button class="button ghost small" @click="download(item.id)">下载</button>
                <button v-if="canWrite" class="button ghost small" @click="remove(item.id)">删除</button>
              </div>
            </td>
          </tr>
          <tr v-if="loading">
            <td colspan="8" class="empty">加载中…</td>
          </tr>
          <tr v-else-if="items.length === 0">
            <td colspan="8" class="empty">暂无材料</td>
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

    <!-- 识别确认：左右分栏 -->
    <div v-if="reviewing" class="recog-mask" @click.self="closeReview">
      <section class="recog-modal" role="dialog" aria-modal="true" aria-label="确认识别结果">
        <header class="recog-head">
          <div>
            <h2>确认识别结果并写入档案</h2>
            <div class="recog-meta">
              <span class="recog-strong">{{ reviewAssetName }}</span>
              <span v-if="reviewPhase === 'loading'" class="badge">识别中</span>
              <span v-if="reviewSource" class="badge">{{ reviewSource === 'ocr' ? 'OCR 识别' : 'PDF 文本层' }}</span>
              <span v-if="reviewWarnings.length" class="badge amber">{{ reviewWarnings.length }} 项需人工判断</span>
            </div>
          </div>
          <button class="icon-button" @click="closeReview" aria-label="关闭">×</button>
        </header>

        <div class="recog-body">
          <aside class="recog-preview">
            <div class="recog-preview-bar">
              <button class="recog-icon" @click="toggleZoom(-0.2)" title="缩小">−</button>
              <span>{{ Math.round(zoom * 100) }}%</span>
              <button class="recog-icon" @click="toggleZoom(0.2)" title="放大">+</button>
              <span style="flex: 1"></span>
              <button class="recog-icon" @click="openOriginal" title="在新标签打开预览">⤢</button>
            </div>
            <div class="recog-sheet-wrap">
              <img
                v-if="previewUrl"
                :src="previewUrl"
                class="recog-sheet"
                :style="{ width: `${zoom * 100}%` }"
                alt="材料预览"
              />
              <p v-else class="hint" style="padding: 20px">{{ previewError || '预览生成中…' }}</p>
            </div>
            <details v-if="reviewPhase === 'ready'" class="recog-ocr">
              <summary>查看识别原文</summary>
              <pre>{{ reviewText }}</pre>
            </details>
          </aside>

          <div class="recog-fields">
            <div class="recog-toolbar">
              <button class="button small" :disabled="applied || reviewPhase !== 'ready'" @click="setBulk('all')">全部写入</button>
              <button class="button small" :disabled="applied || reviewPhase !== 'ready'" @click="setBulk('empty')">只填空白项</button>
              <button class="button small" :disabled="applied || reviewPhase !== 'ready'" @click="setBulk('none')">全部取消</button>
              <span style="flex: 1"></span>
              <button class="button small ghost" @click="closeReview">关闭</button>
            </div>

            <div v-if="reviewPhase === 'loading'" class="recog-state" role="status" aria-live="polite">
              <span class="spinner" aria-hidden="true"></span>
              <strong>正在识别文件内容…</strong>
              <p>PDF 文本层解析通常几秒内完成，扫描件 OCR 可能需要更久；识别完成后会自动填入下方表格。</p>
            </div>

            <div v-else-if="reviewPhase === 'error'" class="recog-state error" role="alert">
              <strong>识别失败</strong>
              <p>{{ reviewError }}</p>
              <button class="button small" @click="retryRecognition">重新识别</button>
            </div>

            <template v-else>
              <div v-if="reviewWarnings.length" class="recog-warn">
                {{ reviewWarnings.join('；') }}
              </div>
              <div v-if="partyExisting && rows.find((r) => r.key === 'patentee')?.state === 'overwrite'" class="recog-warn">
                专利权人识别值与档案现有权利人不同，请确认后再勾选。
              </div>

              <div class="recog-table-wrap">
                <table class="recog-table">
                  <thead>
                    <tr>
                      <th style="width: 52px">写入</th>
                      <th style="width: 120px">字段</th>
                      <th style="width: 200px">档案当前值</th>
                      <th>识别结果（可修改）</th>
                      <th style="width: 84px">状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in rows" :key="row.key">
                      <td>
                        <input
                          v-model="row.checked"
                          type="checkbox"
                          class="recog-check"
                          :disabled="applied || row.readonly || row.state === 'same' || row.state === 'none'"
                        />
                      </td>
                      <td class="recog-label">{{ row.label }}</td>
                      <td class="recog-current" :class="{ empty: !row.current || row.current === '—' }">
                        {{ row.current || '未填写' }}
                      </td>
                      <td>
                        <input
                          :value="row.value"
                          class="field"
                          style="width: 100%"
                          :readonly="row.readonly"
                          @input="onValueInput(row, $event)"
                        />
                      </td>
                      <td>
                        <span class="badge" :class="row.state === 'new' ? 'green' : row.state === 'overwrite' ? 'amber' : 'gray'">
                          {{ stateLabels[row.state] }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>

            <footer class="recog-foot">
              <span v-if="reviewPhase === 'ready'" class="hint">{{ applied ? '本次识别结果已写入档案' : summaryText }}</span>
              <span v-else-if="reviewPhase === 'loading'" class="hint">正在识别，请稍候…</span>
              <span style="flex: 1"></span>
              <span v-if="applyMessage" class="hint" style="margin-right: 10px">{{ applyMessage }}</span>
              <button class="button ghost" @click="closeReview">取消</button>
              <button
                class="button primary"
                :disabled="applying || applied || reviewPhase !== 'ready' || checkedRows.length === 0"
                @click="applyReview"
              >
                {{ applied ? '已写入' : applying ? '写入中…' : '写入档案' }}
              </button>
            </footer>
          </div>
        </div>
      </section>
    </div>

    <!-- 在线查看：复用识别时的服务端预览图，PDF 可逐页翻看 -->
    <div v-if="viewing" class="viewer-mask" @click.self="closeViewer">
      <section class="viewer-modal" role="dialog" aria-modal="true" aria-label="查看材料">
        <header class="viewer-head">
          <div>
            <h2>{{ viewItem?.display_name }}</h2>
            <div class="recog-meta">
              <span>{{ viewItem?.asset_name || '未关联案件' }}</span>
              <span v-if="viewItem">· {{ fileTypeLabel(viewItem) }}</span>
              <span v-if="viewItem">· {{ categoryLabels[viewItem.category] ?? viewItem.category }}</span>
              <span v-if="viewItem?.remark">· 备注：{{ viewItem.remark }}</span>
            </div>
          </div>
          <button class="icon-button" @click="closeViewer" aria-label="关闭">×</button>
        </header>
        <div v-if="viewKind !== 'other'" class="viewer-toolbar">
          <template v-if="viewPageCount > 1">
            <button class="recog-icon" :disabled="viewPage <= 0 || viewLoading" title="上一页" @click="changeViewPage(-1)">‹</button>
            <span>第 {{ viewPage + 1 }} / {{ viewPageCount }} 页</span>
            <button class="recog-icon" :disabled="viewPage >= viewPageCount - 1 || viewLoading" title="下一页" @click="changeViewPage(1)">›</button>
          </template>
          <span v-else>第 1 / 1 页</span>
          <span style="flex: 1"></span>
          <button class="recog-icon" title="缩小" @click="toggleViewZoom(-0.2)">−</button>
          <span>{{ Math.round(viewZoom * 100) }}%</span>
          <button class="recog-icon" title="放大" @click="toggleViewZoom(0.2)">+</button>
        </div>
        <div class="viewer-body">
          <div v-if="viewLoading" class="viewer-state" role="status">
            <span class="spinner" aria-hidden="true"></span>
            <p>正在加载原件…</p>
          </div>
          <p v-else-if="viewError" class="viewer-state viewer-error" role="alert">{{ viewError }}</p>
          <div v-else-if="viewUrl" class="viewer-image-wrap">
            <img
              :src="viewUrl"
              class="viewer-image"
              :style="{ width: `${viewZoom * 100}%` }"
              alt="原件预览"
            />
          </div>
          <div v-else class="viewer-state">
            <p>{{ viewItem ? fileTypeLabel(viewItem) : '该类型' }} 文件不支持浏览器内预览，请点击下方“下载文件”查看。</p>
          </div>
        </div>
        <footer class="viewer-foot">
          <button class="button ghost" @click="closeViewer">关闭</button>
          <button v-if="viewItem" class="button primary" @click="downloadViewed">下载文件</button>
        </footer>
      </section>
    </div>

    <div v-if="uploadOpen">
      <div class="drawer-backdrop" @click="closeUpload"></div>
      <aside
        ref="uploadDrawer"
        class="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="上传资料"
        tabindex="-1"
        @keydown.esc="closeUpload"
      >
        <header>
          <small>材料中心</small>
          <h2>上传资料</h2>
        </header>
        <div class="drawer-body">
          <div class="form-grid">
            <div class="form-item full">
              <label>关联案件 <em>*</em></label>
              <AssetPicker v-model="assetId" :assets="assets" :search="searchAssets" placeholder="输入案件名称或我方文号搜索（必选）" />
            </div>
            <div class="form-item full">
              <label for="upload_category">分类</label>
              <select id="upload_category" v-model="category">
                <option v-for="(label, value) in categoryLabels" :key="value" :value="value">{{ label }}</option>
              </select>
            </div>
            <div class="form-item full">
              <label>文件 <em>*</em></label>
              <div class="file-picker">
                <input id="upload_file" ref="fileInput" type="file" class="hidden-file" @change="onFileChange" />
                <label for="upload_file" class="button small file-trigger">选择文件</label>
                <span v-if="selectedFile" class="file-name">{{ selectedFile.name }} · {{ humanSize(selectedFile.size) }}</span>
                <span v-else class="hint">未选择文件</span>
                <button v-if="selectedFile" type="button" class="link-button" @click="clearSelectedFile">清除</button>
              </div>
              <small class="hint">允许 PDF、图片、Office 文档与 ZIP；单文件上限由后端配置控制。</small>
            </div>
            <div class="form-item full">
              <label>类型</label>
              <div class="readonly-value">{{ selectedFileTypeLabel() }}</div>
              <small class="hint">根据文件扩展名自动判断；仅 PDF 和图片支持识别。</small>
            </div>
            <div class="form-item full">
              <label for="upload_remark">备注</label>
              <textarea id="upload_remark" v-model="remark" maxlength="500" placeholder="可选，最多 500 字"></textarea>
            </div>
          </div>
          <p v-if="uploadError" class="error-text" style="margin-top: 12px">{{ uploadError }}</p>
        </div>
        <footer>
          <button class="button ghost" :disabled="uploading" @click="closeUpload">取消</button>
          <button class="button primary" :disabled="uploading || !assetId || !selectedFile" @click="upload">
            {{ uploading ? '上传中…' : '上传资料' }}
          </button>
        </footer>
      </aside>
    </div>

    <div v-if="editing && editItem">
      <div class="drawer-backdrop" @click="closeEdit"></div>
      <aside
        ref="editDrawer"
        class="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="修改材料"
        tabindex="-1"
        @keydown.esc="closeEdit"
      >
        <header>
          <small>材料中心</small>
          <h2>修改材料</h2>
        </header>
        <div class="drawer-body">
          <div class="edit-current">
            <div class="edit-current-main">
              <strong>{{ editItem.display_name }}</strong>
              <small>{{ editItem.original_name }} · {{ humanSize(editItem.size_bytes) }}</small>
            </div>
            <span class="badge gray">{{ fileTypeLabel(editItem) }}</span>
            <span class="badge">{{ categoryLabels[editItem.category] ?? editItem.category }}</span>
          </div>

          <div class="form-grid" style="margin-top: 18px">
            <div class="form-item full">
              <label>关联案件</label>
              <div class="readonly-value">
                <RouterLink v-if="editItem.ip_asset_id" :to="`/assets/${editItem.ip_asset_id}`" class="name-link">
                  {{ editItem.asset_name || '未命名案件' }}
                </RouterLink>
                <span v-else class="hint">未关联案件</span>
              </div>
            </div>
            <div class="form-item full">
              <label for="edit_file">更换文件</label>
              <div class="file-picker">
                <input id="edit_file" ref="editFileInput" type="file" class="hidden-file" @change="onEditFileChange" />
                <label for="edit_file" class="button small file-trigger">选择新文件</label>
                <span v-if="editFile" class="file-name">将替换为：{{ editFile.name }} · {{ humanSize(editFile.size) }}</span>
                <span v-else class="hint">当前文件保持不变</span>
                <button v-if="editFile" type="button" class="link-button" @click="clearEditFile">取消更换</button>
              </div>
              <small class="hint">不选择文件则只更新备注；更换后旧文件保留在存储层，识别结果会重置。</small>
            </div>
            <div class="form-item full">
              <label for="edit_remark">备注</label>
              <textarea id="edit_remark" v-model="editRemark" maxlength="500" placeholder="最多 500 字"></textarea>
            </div>
          </div>
          <p v-if="editError" class="error-text" style="margin-top: 12px">{{ editError }}</p>
        </div>
        <footer>
          <button class="button ghost" :disabled="editSaving" @click="closeEdit">取消</button>
          <button class="button primary" :disabled="editSaving" @click="saveEdit">
            {{ editSaving ? '保存中…' : '保存' }}
          </button>
        </footer>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.recog-mask {
  position: fixed;
  inset: 0;
  background: rgba(7, 18, 38, 0.55);
  z-index: 200;
  display: grid;
  place-items: center;
  padding: 20px;
}
.recog-modal {
  width: 1180px;
  max-width: 100%;
  height: 86vh;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.recog-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
}
.recog-head h2 {
  font-size: 17px;
  margin: 0 0 6px;
}
.recog-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--muted);
  flex-wrap: wrap;
}
.recog-strong {
  color: var(--ink);
  font-weight: 600;
}
.recog-body {
  display: grid;
  grid-template-columns: 400px 1fr;
  flex: 1;
  min-height: 0;
}
.recog-preview {
  border-right: 1px solid var(--line);
  background: #eef2f7;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.recog-preview-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #fff;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
  color: var(--muted);
}
.recog-icon {
  width: 26px;
  height: 26px;
  border: 1px solid var(--line);
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  color: #475269;
}
.recog-icon:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.recog-sheet-wrap {
  flex: 1;
  overflow: auto;
  padding: 14px;
  display: grid;
  place-items: start center;
}
.recog-sheet {
  display: block;
  max-width: 100%;
  height: auto;
  background: #fff;
  box-shadow: 0 6px 24px rgba(25, 45, 76, 0.16);
}
.recog-ocr {
  border-top: 1px solid var(--line);
  background: #fff;
}
.recog-ocr summary {
  padding: 9px 12px;
  font-size: 12px;
  color: var(--blue);
  cursor: pointer;
}
.recog-ocr pre {
  margin: 0;
  padding: 0 12px 12px;
  font-size: 11px;
  color: var(--muted);
  white-space: pre-wrap;
  max-height: 110px;
  overflow: auto;
}
.recog-fields {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.recog-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--line);
  background: #fbfcfe;
}
.recog-warn {
  margin: 10px 16px 0;
  background: #fff9ec;
  border: 1px solid #fae4b7;
  border-radius: 9px;
  padding: 9px 11px;
  font-size: 12px;
  color: #8b6b36;
}
.recog-table-wrap {
  flex: 1;
  overflow: auto;
  padding: 10px 16px 0;
}
.recog-table {
  width: 100%;
  border-collapse: collapse;
}
.recog-table th {
  position: sticky;
  top: 0;
  background: #fff;
  text-align: left;
  font-size: 11px;
  color: #778298;
  font-weight: 600;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
}
.recog-table td {
  padding: 8px 10px;
  border-bottom: 1px solid #f0f2f6;
  font-size: 13px;
  vertical-align: middle;
}
.recog-check {
  width: 16px;
  height: 16px;
  accent-color: var(--blue);
  cursor: pointer;
}
.recog-label {
  color: #475269;
  font-size: 12px;
  white-space: nowrap;
}
.recog-current {
  color: var(--muted);
  font-size: 12px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recog-current.empty {
  color: #b6becb;
  font-style: italic;
}
.recog-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid var(--line);
  background: #fff;
}
.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #d7e2f2;
  border-top-color: var(--blue);
  border-radius: 50%;
  animation: ipms-spin 0.8s linear infinite;
  display: inline-block;
  flex: none;
}
.spinner.small {
  width: 12px;
  height: 12px;
  margin-right: 5px;
  vertical-align: -2px;
}
@keyframes ipms-spin {
  to {
    transform: rotate(360deg);
  }
}
.recog-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 28px;
  text-align: center;
  color: var(--muted);
}
.recog-state strong {
  color: var(--ink);
  font-size: 14px;
}
.recog-state p {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  max-width: 440px;
}
.recog-state.error strong,
.recog-state.error p {
  color: #a94442;
}
.viewer-mask {
  position: fixed;
  inset: 0;
  background: rgba(7, 18, 38, 0.6);
  z-index: 210;
  display: grid;
  place-items: center;
  padding: 20px;
}
.viewer-modal {
  width: 1040px;
  max-width: 100%;
  height: 88vh;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.viewer-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
}
.viewer-head h2 {
  font-size: 17px;
  margin: 0 0 6px;
  word-break: break-all;
}
.viewer-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #3d4654;
}
.viewer-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #fbfcfe;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
  color: var(--muted);
}
.viewer-image-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: grid;
  place-items: start center;
  padding: 16px;
}
.viewer-image {
  height: auto;
  max-width: none;
  background: #fff;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.25);
}
.viewer-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 28px;
  text-align: center;
  color: #e6edf6;
}
.viewer-state p {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  max-width: 460px;
}
.viewer-error {
  color: #ffd7d7;
}
.viewer-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--line);
  background: #fff;
}

/* 材料操作结果提示 */
.success-banner {
  margin: 0 0 12px;
  padding: 10px 14px;
  border: 1px solid #bfe6d2;
  background: #f0fbf5;
  border-radius: 10px;
  font-size: 12px;
  color: #16865a;
}

/* 文件选择：隐藏原生控件，用按钮触发 */
.file-picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px dashed var(--line);
  border-radius: 9px;
  background: #fbfcfe;
}
.hidden-file {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.file-trigger {
  font-size: 12px;
  color: #344054;
  cursor: pointer;
}
.file-trigger:hover {
  color: var(--blue);
  border-color: #9fbdf8;
}
.file-name {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.form-item label em {
  color: var(--red);
  font-style: normal;
}
.link-button {
  border: 0;
  background: transparent;
  color: var(--blue);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
  flex: none;
}

/* 修改材料抽屉 */
.edit-current {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 14px;
  background: #f7f9fc;
  border: 1px solid var(--line);
  border-radius: 10px;
}
.edit-current-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.edit-current-main strong {
  font-size: 13px;
  word-break: break-all;
}
.edit-current-main small {
  font-size: 11px;
  color: var(--muted);
  word-break: break-all;
}
.readonly-value {
  font-size: 13px;
}
</style>
