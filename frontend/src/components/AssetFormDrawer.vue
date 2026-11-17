<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { useToast } from '../toast'

const props = defineProps<{
  open: boolean
  assetId: string | null
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'saved'): void
}>()

const toast = useToast()
const saving = ref(false)
const formError = ref('')
const editingId = ref<string | null>(null)
const editingPartyId = ref<string | null>(null)
const originalParty = ref({ name: '', party_type: 'company' })

const form = reactive({
  docket_no: '',
  name: '',
  ip_type: 'patent',
  status_group: 'in_progress',
  patent_type: 'invention',
  application_no: '',
  application_date: '',
  publication_no: '',
  publication_date: '',
  grant_date: '',
  legal_status: '',
  party_name: '',
  party_type: 'company',
  rights_mode: '',
  certificate_date: '',
  remark: '',
  word_mark: '',
  mark_type: 'combined',
  tm_application_no: '',
  tm_application_date: '',
  registration_no: '',
  registration_date: '',
  valid_to: '',
  classes: '',
})

function resetForm() {
  Object.assign(form, {
    docket_no: '',
    name: '',
    ip_type: 'patent',
    status_group: 'in_progress',
    patent_type: 'invention',
    application_no: '',
    application_date: '',
    publication_no: '',
    publication_date: '',
    grant_date: '',
    legal_status: '',
    party_name: '',
    party_type: 'company',
    rights_mode: '',
    certificate_date: '',
    remark: '',
    word_mark: '',
    mark_type: 'combined',
    tm_application_no: '',
    tm_application_date: '',
    registration_no: '',
    registration_date: '',
    valid_to: '',
    classes: '',
  })
}

function openDrawer() {
  formError.value = ''
  editingId.value = null
  editingPartyId.value = null
  originalParty.value = { name: '', party_type: 'company' }
  resetForm()
}

async function openEdit(id: string) {
  formError.value = ''
  try {
    const detail = await api.asset(id)
    const patent = (detail.patent ?? {}) as Record<string, unknown>
    const copyright = (detail.copyright ?? {}) as Record<string, unknown>
    const trademark = (detail.trademark ?? {}) as Record<string, unknown>
    const party = detail.parties[0]
    editingPartyId.value = party?.id ?? null
    originalParty.value = { name: party?.name ?? '', party_type: party?.party_type ?? 'company' }
    editingId.value = id
    Object.assign(form, {
      docket_no: detail.docket_no ?? '',
      name: detail.name,
      ip_type: detail.ip_type,
      status_group: detail.status_group,
      patent_type: String(patent.patent_type ?? 'invention'),
      application_no: String(patent.application_no ?? ''),
      application_date: String(patent.application_date ?? ''),
      publication_no: String(patent.publication_no ?? ''),
      publication_date: String(patent.publication_date ?? ''),
      grant_date: String(patent.grant_date ?? ''),
      legal_status: String(patent.legal_status ?? ''),
      party_name: party?.name ?? '',
      party_type: party?.party_type ?? 'company',
      rights_mode: String(copyright.rights_mode ?? ''),
      certificate_date: String(copyright.certificate_date ?? ''),
      remark: detail.remark ?? '',
      word_mark: String(trademark.word_mark ?? ''),
      mark_type: String(trademark.mark_type ?? 'combined'),
      tm_application_no: String(trademark.application_no ?? ''),
      tm_application_date: String(trademark.application_date ?? ''),
      registration_no: String(trademark.registration_no ?? ''),
      registration_date: String(trademark.registration_date ?? ''),
      valid_to: String(trademark.valid_to ?? ''),
      classes: Array.isArray(trademark.classes) ? (trademark.classes as string[]).join('、') : String(trademark.classes ?? ''),
    })
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '读取档案失败'
  }
}

async function save() {
  formError.value = ''
  if (!form.name.trim()) {
    formError.value = form.ip_type === 'copyright' ? '软件名称必填' : '案件名称必填'
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      let linkedParties: Array<{ party_id: string; role: string; seq: number }> | undefined
      if (form.ip_type === 'copyright' && form.party_name.trim()) {
        const name = form.party_name.trim()
        if (editingPartyId.value) {
          if (name !== originalParty.value.name || form.party_type !== originalParty.value.party_type) {
            await api.updateParty(editingPartyId.value, { name, party_type: form.party_type })
            originalParty.value = { name, party_type: form.party_type }
          }
        } else {
          const party = await api.createParty({ name, party_type: form.party_type })
          editingPartyId.value = party.id
          originalParty.value = { name, party_type: form.party_type }
          linkedParties = [{ party_id: party.id, role: 'copyright_owner', seq: 0 }]
        }
      }
      await api.updateAsset(editingId.value, {
        name: form.name.trim(),
        docket_no: form.docket_no.trim() || null,
        status_group: form.status_group,
        remark: form.remark.trim() || null,
        ...(form.ip_type === 'copyright'
          ? {
              copyright: {
                rights_mode: form.rights_mode || null,
                certificate_date: form.certificate_date || null,
              },
            }
          : {}),
        ...(linkedParties ? { parties: linkedParties } : {}),
        ...(form.ip_type === 'patent'
          ? {
              patent: {
                patent_type: form.patent_type,
                application_no: form.application_no || null,
                application_date: form.application_date || null,
                publication_no: form.publication_no || null,
                publication_date: form.publication_date || null,
                grant_date: form.grant_date || null,
                legal_status: form.legal_status.trim() || null,
              },
            }
          : {}),
        ...(form.ip_type === 'trademark'
          ? {
              trademark: {
                word_mark: form.word_mark || null,
                mark_type: form.mark_type,
                application_no: form.tm_application_no || null,
                application_date: form.tm_application_date || null,
                registration_no: form.registration_no || null,
                registration_date: form.registration_date || null,
                valid_to: form.valid_to || null,
                classes: form.classes ? form.classes.split(/[,，、\s]+/).filter(Boolean) : null,
              },
            }
          : {}),
      })
    } else {
      const payload: Record<string, unknown> = {
        name: form.name.trim(),
        docket_no: form.ip_type === 'copyright' ? null : form.docket_no.trim() || null,
        ip_type: form.ip_type,
        status_group: form.status_group,
        remark: form.remark.trim() || null,
      }
      if (form.ip_type === 'patent') {
        payload.patent = {
          patent_type: form.patent_type,
          application_no: form.application_no || null,
          application_date: form.application_date || null,
          publication_no: form.publication_no || null,
          publication_date: form.publication_date || null,
          grant_date: form.grant_date || null,
          legal_status: form.legal_status.trim() || null,
        }
      } else if (form.ip_type === 'copyright') {
        payload.copyright = {
          rights_mode: form.rights_mode.trim() || null,
          certificate_date: form.certificate_date || null,
        }
        if (form.party_name.trim()) {
          payload.copyright_owner = {
            name: form.party_name.trim(),
            party_type: form.party_type,
          }
        }
      } else {
        payload.trademark = {
          word_mark: form.word_mark || null,
          mark_type: form.mark_type,
          application_no: form.tm_application_no || null,
          application_date: form.tm_application_date || null,
          registration_no: form.registration_no || null,
          registration_date: form.registration_date || null,
          valid_to: form.valid_to || null,
          classes: form.classes ? form.classes.split(/[,，、\s]+/).filter(Boolean) : null,
        }
      }
      await api.createAsset(payload)
    }
    toast.success(editingId.value ? '档案已保存' : '档案已新建')
    emit('saved')
  } catch (err) {
    formError.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      if (props.assetId) void openEdit(props.assetId)
      else openDrawer()
    }
  },
)
</script>

<template>
  <div v-if="open">
    <div class="drawer-backdrop" @click="emit('close')"></div>
    <aside
      class="drawer"
      role="dialog"
      aria-modal="true"
      :aria-label="editingId ? '编辑档案' : '新建档案'"
      tabindex="-1"
      @keydown.esc="emit('close')"
    >
      <header>
        <small>知识产权档案</small>
        <h2>{{ editingId ? '编辑档案' : '新建档案' }}</h2>
      </header>
      <div class="drawer-body">
        <div class="form-grid">
          <div class="form-item full">
            <label for="name">{{ form.ip_type === 'copyright' ? '软件名称' : '案件名称' }} *</label>
            <input id="name" v-model="form.name" :placeholder="form.ip_type === 'copyright' ? '请输入软件名称' : '请输入案件名称'" />
          </div>
          <div class="form-item">
            <label for="ip_type">知识产权类型 *</label>
            <select id="ip_type" v-model="form.ip_type" :disabled="Boolean(editingId)">
              <option value="patent">专利</option>
              <option value="copyright">软件著作权</option>
              <option value="trademark">商标 / Logo</option>
            </select>
          </div>
          <div v-if="form.ip_type !== 'copyright'" class="form-item">
            <label for="docket_no">我方文号</label>
            <input id="docket_no" v-model="form.docket_no" placeholder="例如 STHL2001-1-A36NF" />
          </div>
          <div class="form-item">
            <label for="status_group">综合状态</label>
            <select id="status_group" v-model="form.status_group">
              <option value="in_progress">办理中</option>
              <option value="granted">已取得权利</option>
              <option value="invalid">已失效</option>
              <option value="other">其他</option>
            </select>
          </div>
          <template v-if="form.ip_type === 'patent'">
            <div class="form-item">
              <label for="patent_type">专利类型</label>
              <select id="patent_type" v-model="form.patent_type">
                <option value="invention">发明专利</option>
                <option value="utility">实用新型</option>
                <option value="design">外观设计</option>
              </select>
            </div>
            <div class="form-item">
              <label for="application_no">申请号</label>
              <input id="application_no" v-model="form.application_no" placeholder="未取得可留空" />
            </div>
            <div class="form-item">
              <label for="application_date">申请日期</label>
              <input id="application_date" v-model="form.application_date" type="date" />
            </div>
            <div class="form-item">
              <label for="publication_no">公开号</label>
              <input id="publication_no" v-model="form.publication_no" maxlength="64" placeholder="未公开可留空" />
            </div>
            <div class="form-item">
              <label for="publication_date">公开日期</label>
              <input id="publication_date" v-model="form.publication_date" type="date" />
            </div>
            <div class="form-item">
              <label for="grant_date">授权公告日</label>
              <input id="grant_date" v-model="form.grant_date" type="date" />
            </div>
            <div class="form-item">
              <label for="legal_status">法律状态</label>
              <input id="legal_status" v-model="form.legal_status" maxlength="64" placeholder="例如：有效 / 实质审查中" />
            </div>
          </template>
          <template v-if="form.ip_type === 'copyright'">
            <div class="form-item">
              <label for="party_name">著作权人</label>
              <input id="party_name" v-model="form.party_name" maxlength="200" placeholder="已有则更新，未关联则新建" />
            </div>
            <div class="form-item">
              <label for="party_type">著作权人类型</label>
              <select id="party_type" v-model="form.party_type">
                <option value="company">企业</option>
                <option value="person">个人</option>
                <option value="organization">组织</option>
              </select>
            </div>
            <div class="form-item">
              <label for="rights_mode">权利取得方式</label>
              <select id="rights_mode" v-model="form.rights_mode">
                <option value="">请选择</option>
                <option value="原始取得">原始取得</option>
                <option value="继受取得">继受取得</option>
                <option value="其他">其他</option>
              </select>
            </div>
            <div class="form-item">
              <label for="certificate_date">授权公告日</label>
              <input id="certificate_date" v-model="form.certificate_date" type="date" />
            </div>
          </template>
          <template v-if="form.ip_type === 'trademark'">
            <div class="form-item">
              <label for="tm_mark_type">商标类型</label>
              <select id="tm_mark_type" v-model="form.mark_type">
                <option value="word">文字商标</option>
                <option value="figurative">图形商标</option>
                <option value="combined">组合商标</option>
              </select>
            </div>
            <div class="form-item">
              <label for="tm_word_mark">商标文字</label>
              <input id="tm_word_mark" v-model="form.word_mark" placeholder="纯图形商标可留空" />
            </div>
            <div class="form-item">
              <label for="tm_application_no">申请号</label>
              <input id="tm_application_no" v-model="form.tm_application_no" />
            </div>
            <div class="form-item">
              <label for="tm_application_date">申请日期</label>
              <input id="tm_application_date" v-model="form.tm_application_date" type="date" />
            </div>
            <div class="form-item">
              <label for="tm_registration_no">注册号</label>
              <input id="tm_registration_no" v-model="form.registration_no" />
            </div>
            <div class="form-item">
              <label for="tm_registration_date">注册日期</label>
              <input id="tm_registration_date" v-model="form.registration_date" type="date" />
            </div>
            <div class="form-item">
              <label for="tm_valid_to">有效期截止</label>
              <input id="tm_valid_to" v-model="form.valid_to" type="date" />
            </div>
            <div class="form-item full">
              <label for="tm_classes">商品 / 服务类别</label>
              <input id="tm_classes" v-model="form.classes" placeholder="逗号或顿号分隔，分类体系待确认" />
            </div>
          </template>
          <div class="form-item full">
            <label for="remark">备注</label>
            <textarea id="remark" v-model="form.remark" placeholder="内部备注，列表页不展示"></textarea>
          </div>
        </div>
        <p v-if="formError" class="error-text" style="margin-top: 12px">{{ formError }}</p>
        <p class="hint" style="margin-top: 12px">专业字段的必填规则与业务编号规则尚待确认。</p>
      </div>
      <footer>
        <button class="button ghost" @click="emit('close')">取消</button>
        <button class="button primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
      </footer>
    </aside>
  </div>
</template>
