<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../api'

interface ImportResult {
  total_rows: number
  created: number
  skipped: number
  errors: Array<{ row: number; message: string }>
}

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'imported', created: number): void }>()
const dialogEl = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const file = ref<File | null>(null)
const dragging = ref(false)
const uploading = ref(false)
const error = ref('')
const result = ref<ImportResult | null>(null)
const completed = ref(false)
let trigger: HTMLElement | null = null

function reset() { file.value = null; error.value = ''; result.value = null; completed.value = false; dragging.value = false; if (fileInput.value) fileInput.value.value = '' }
function chooseOtherFile() { reset(); void nextTick(() => fileInput.value?.click()) }
watch(() => props.open, (value) => {
  if (value) { trigger = document.activeElement as HTMLElement | null; reset(); document.body.style.overflow = 'hidden'; void nextTick(() => dialogEl.value?.focus()) }
  else { document.body.style.overflow = ''; trigger?.focus() }
})
onBeforeUnmount(() => { document.body.style.overflow = '' })
function close() { emit('close') }
function selectFile(candidate?: File) {
  if (!candidate) return
  if (!/\.(csv|xlsx)$/i.test(candidate.name)) { error.value = '仅支持 CSV 或 XLSX 文件'; return }
  file.value = candidate; error.value = ''; result.value = null; completed.value = false
}
function choose(event: Event) { selectFile((event.target as HTMLInputElement).files?.[0]) }
function drop(event: DragEvent) { dragging.value = false; selectFile(event.dataTransfer?.files?.[0]) }
async function upload() {
  if (!file.value) { error.value = '请选择 CSV 或 XLSX 文件'; return }
  uploading.value = true; error.value = ''
  try { result.value = await api.importAssets(file.value); completed.value = true; emit('imported', result.value.created) }
  catch (err) { error.value = err instanceof Error ? err.message : '导入失败' }
  finally { uploading.value = false }
}
function downloadTemplate() {
  const content = '\ufeff我方文号,申请号,案件名称,专利所有权人,官费应缴纳日,本次官费缴纳至,本次官费缴纳金额,缴纳日期\n'
  const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8' }))
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = '知识产权导入模板.csv'; anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

async function downloadXlsxTemplate() {
  try { await api.downloadImportTemplate() }
  catch (err) { error.value = err instanceof Error ? err.message : '模板下载失败' }
}
</script>

<template>
  <div v-if="open" class="import-mask" @click.self="close" @keydown.esc="close">
    <section ref="dialogEl" class="import-dialog" role="dialog" aria-modal="true" aria-label="导入档案" tabindex="-1" :aria-busy="uploading">
      <header><div><small>工作台 · 数据维护</small><h2>导入知识产权档案</h2></div><button class="icon-button" aria-label="关闭" @click="close">×</button></header>
      <div class="import-body">
        <div class="import-note"><strong>CSV / XLSX 字段说明</strong><p><code>案件名称</code> 为必填；<code>我方文号</code>、<code>申请号</code>、<code>专利所有权人</code>、<code>官费应缴纳日</code>、<code>本次官费缴纳至</code>、<code>本次官费缴纳金额</code>、<code>缴纳日期</code> 可选。日期格式 <code>YYYY-MM-DD</code>，金额最多两位小数。XLSX 读取第一个工作表；CSV 必须为 UTF-8。</p><div style="display:flex;gap:8px"><button class="button small" @click="downloadTemplate">⇩ CSV 模板</button><button class="button small" @click="downloadXlsxTemplate">⇩ XLSX 模板</button></div></div>
        <div class="drop-zone" :class="{ dragging }" role="button" tabindex="0" aria-label="选择或拖放 CSV 或 XLSX 文件" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="drop" @click="fileInput?.click()" @keydown.enter.prevent="fileInput?.click()" @keydown.space.prevent="fileInput?.click()">
          <input ref="fileInput" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden @change="choose" />
          <strong>{{ file ? file.name : '拖放 CSV 或 XLSX 文件到这里' }}</strong><p>{{ file ? `${Math.ceil(file.size / 1024)} KB · 点击可重新选择` : '或点击选择文件' }}</p>
        </div>
        <p v-if="error" class="error-text" role="alert">{{ error }}</p>
        <div v-if="result" class="import-result" aria-live="polite">
          <div class="import-stats"><div><span>总行数</span><strong>{{ result.total_rows }}</strong></div><div><span>成功</span><strong class="success">{{ result.created }}</strong></div><div><span>跳过</span><strong class="warning">{{ result.skipped }}</strong></div></div>
          <div v-if="result.errors.length" class="error-list"><h3>错误明细</h3><table class="data"><thead><tr><th>行号</th><th>原因</th></tr></thead><tbody><tr v-for="item in result.errors" :key="`${item.row}-${item.message}`"><td>{{ item.row || '数据库' }}</td><td>{{ item.message }}</td></tr></tbody></table></div>
          <p v-else class="hint">全部行导入成功。</p>
        </div>
        <p class="hint">导入会创建档案主数据、专利子档案，并根据填写的列同步创建专利权人和官费记录；空白可选列不会生成对应数据。导入会记录审计。</p>
      </div>
      <footer><button class="button ghost" @click="close">关闭</button><button v-if="completed" class="button" @click="chooseOtherFile">继续上传其他文件</button><button v-else class="button primary" :disabled="uploading || !file" @click="upload">{{ uploading ? '导入中…' : '开始导入' }}</button></footer>
    </section>
  </div>
</template>

<style scoped>
.import-mask{position:fixed;inset:0;z-index:220;background:rgba(7,18,38,.55);display:grid;place-items:center;padding:20px}.import-dialog{width:760px;max-width:100%;max-height:88vh;background:#fff;border-radius:14px;box-shadow:0 30px 80px rgba(0,0,0,.35);display:flex;flex-direction:column;overflow:hidden}.import-dialog header,.import-dialog footer{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:flex-start}.import-dialog header small{color:var(--blue)}.import-dialog h2{font-size:17px;margin:4px 0 0}.import-dialog footer{border:0;border-top:1px solid var(--line);justify-content:flex-end;gap:8px}.import-body{padding:18px 20px;overflow:auto}.import-note{background:#f7faff;border:1px solid #dce8fb;border-radius:10px;padding:12px;margin-bottom:12px}.import-note p{color:var(--muted);font-size:12px}.drop-zone{border:2px dashed #b9c8de;border-radius:12px;padding:30px;text-align:center;cursor:pointer;background:#fbfcfe}.drop-zone.dragging{border-color:var(--blue);background:#eef4ff}.drop-zone p{color:var(--muted);font-size:12px}.import-result{margin-top:15px}.import-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}.import-stats>div{border:1px solid var(--line);border-radius:10px;padding:12px}.import-stats span{display:block;color:var(--muted);font-size:11px}.import-stats strong{display:block;font-size:22px;margin-top:4px}.success{color:var(--green)}.warning{color:var(--amber)}.error-list{margin-top:13px;max-height:230px;overflow:auto}.error-list h3{font-size:13px}.icon-button{border:0;background:transparent;font-size:20px;color:var(--muted)}
</style>
