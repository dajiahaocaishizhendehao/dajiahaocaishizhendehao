<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, formatDate, statusLabels, typeLabels, type AssetDetail } from '../api'
import { actionLabels, markTypeLabels, partyTypeLabels, patentTypeLabels, personTypeLabels } from '../labels'
import { useAuth } from '../auth'
import { useToast } from '../toast'
import AssetFormDrawer from '../components/AssetFormDrawer.vue'

const route = useRoute()
const { canWrite, canAdmin } = useAuth()
const toast = useToast()
const asset = ref<AssetDetail | null>(null)
const loading = ref(true)
const error = ref('')
const showEdit = ref(false)
const tab = ref<'overview' | 'audit'>('overview')
const auditLogs = ref<Array<{ id: string; action: string; summary: string | null; ip_address: string | null; created_at: string }>>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditLoading = ref(false)

interface PersonOption {
  id: string
  name: string
  person_type: string
}

const showPersonDrawer = ref(false)
const personOptions = ref<PersonOption[]>([])
const selectedPersons = ref<PersonOption[]>([])
const personSearch = ref('')
const personLoading = ref(false)
const personSaving = ref(false)
const creatingPerson = ref(false)
const personError = ref('')
const newPerson = reactive({ name: '', person_type: 'inventor' })

const patentLabels: Array<[string, string]> = [
  ['patent_type', '专利类型'],
  ['application_no', '申请号'],
  ['application_date', '申请日期'],
  ['publication_no', '公开号'],
  ['publication_date', '公开日期'],
  ['patent_no', '专利号'],
  ['grant_date', '授权公告日'],
  ['legal_status', '法律状态'],
]

const trademarkLabels: Array<[string, string]> = [
  ['word_mark', '商标文字'],
  ['mark_type', '商标类型'],
  ['registration_no', '注册号'],
  ['registration_date', '注册日期'],
  ['application_no', '申请号'],
  ['application_date', '申请日期'],
  ['valid_from', '有效期开始'],
  ['valid_to', '有效期截止'],
  ['classes', '商品 / 服务类别'],
  ['color_desc', '颜色说明'],
  ['country', '申请国家 / 地区'],
  ['agent_name', '代理人'],
]

function formatValue(raw: unknown): string {
  if (raw === null || raw === undefined || raw === '') return '—'
  if (Array.isArray(raw)) return raw.join('、')
  if (typeof raw === 'string' && /^\d{4}-\d{2}-\d{2}/.test(raw)) return raw.slice(0, 10)
  return String(raw)
}

const labels = computed<Array<[string, string]>>(() => {
  if (!asset.value) return []
  if (asset.value.ip_type === 'patent') return patentLabels
  if (asset.value.ip_type === 'trademark') return trademarkLabels
  return []
})

// 软著只展示与新建 / 编辑抽屉一致的字段：著作权人、著作权人类型、权利取得方式、
// 授权公告日、备注；其余软著专业字段仍保存在数据库和 API 中，暂不在详情页展示。
const copyrightRows = computed(() => {
  if (!asset.value || asset.value.ip_type !== 'copyright') return []
  const record = (asset.value.copyright ?? {}) as Record<string, unknown>
  const party = asset.value.parties[0]
  return [
    { key: 'party_name', label: '著作权人', value: party?.name ? party.name : '—' },
    {
      key: 'party_type',
      label: '著作权人类型',
      value: party ? partyTypeLabels[party.party_type] ?? party.party_type : '—',
    },
    { key: 'rights_mode', label: '权利取得方式', value: formatValue(record.rights_mode) },
    { key: 'certificate_date', label: '授权公告日', value: formatValue(record.certificate_date) },
    { key: 'remark', label: '备注', value: formatValue(asset.value.remark) },
  ]
})

const professionalRows = computed(() => {
  if (!asset.value) return []
  if (asset.value.ip_type === 'copyright') return copyrightRows.value
  const record = (asset.value.patent ?? asset.value.trademark) as Record<string, unknown> | null
  if (!record) return []

  return labels.value.map(([key, label]) => {
    const raw = record[key]
    let value = '—'
    if (raw !== null && raw !== undefined && raw !== '') {
      if (key === 'patent_type') value = patentTypeLabels[String(raw)] ?? String(raw)
      else if (key === 'mark_type') value = markTypeLabels[String(raw)] ?? String(raw)
      else if (Array.isArray(raw)) value = raw.join('、')
      else if (typeof raw === 'string' && /^\d{4}-\d{2}-\d{2}/.test(raw)) value = raw.slice(0, 10)
      else value = String(raw)
    }
    return { key, label, value }
  })
})

const hasProfessional = computed(() => {
  if (!asset.value) return false
  if (asset.value.ip_type === 'copyright') return true
  return professionalRows.value.some((row) => row.value !== '—')
})

const relatedLinks = computed(() => {
  if (!asset.value) return []
  const id = asset.value.id
  return [
    { to: `/dates?asset=${id}`, title: '日期事项', desc: '该案件的提醒与期限' },
    { to: `/materials?asset=${id}`, title: '材料', desc: '该案件的电子材料' },
    { to: `/fees?asset=${id}`, title: '费用', desc: '该案件的官费与代理费' },
  ]
})

async function load() {
  loading.value = true
  try {
    asset.value = await api.asset(String(route.params.id))
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function onEditSaved() {
  showEdit.value = false
  void load()
}

async function loadAuditLogs() {
  if (!asset.value) return
  auditLoading.value = true
  try {
    const result = await api.auditLogs({
      object_type: 'ip_asset',
      object_id: asset.value.id,
      page: auditPage.value,
      page_size: 20,
    })
    auditLogs.value = result.items as unknown as typeof auditLogs.value
    auditTotal.value = result.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '审计日志加载失败'
  } finally {
    auditLoading.value = false
  }
}

function switchTab(next: 'overview' | 'audit') {
  tab.value = next
  if (next === 'audit') {
    auditPage.value = 1
    void loadAuditLogs()
  }
}

const availablePersons = computed(() =>
  personOptions.value.filter((option) => !selectedPersons.value.some((person) => person.id === option.id)),
)

async function searchPersons() {
  personLoading.value = true
  personError.value = ''
  try {
    const page = await api.persons({
      q: personSearch.value.trim() || undefined,
      page: 1,
      page_size: 50,
    })
    personOptions.value = page.items as unknown as PersonOption[]
  } catch (err) {
    personError.value = err instanceof Error ? err.message : '人员加载失败'
  } finally {
    personLoading.value = false
  }
}

async function openPersonDrawer() {
  if (!asset.value) return
  selectedPersons.value = [...asset.value.persons]
  personSearch.value = ''
  newPerson.name = ''
  newPerson.person_type = 'inventor'
  personError.value = ''
  showPersonDrawer.value = true
  await searchPersons()
}

function closePersonDrawer() {
  if (personSaving.value) return
  showPersonDrawer.value = false
}

function addPerson(option: PersonOption) {
  if (selectedPersons.value.some((person) => person.id === option.id)) return
  selectedPersons.value.push({ id: option.id, name: option.name, person_type: option.person_type })
}

function removePerson(id: string) {
  selectedPersons.value = selectedPersons.value.filter((person) => person.id !== id)
}

async function createPerson() {
  if (!newPerson.name.trim()) {
    personError.value = '请输入人员姓名'
    return
  }
  creatingPerson.value = true
  personError.value = ''
  try {
    const created = (await api.createPerson({
      name: newPerson.name.trim(),
      person_type: newPerson.person_type,
    })) as unknown as PersonOption
    addPerson(created)
    newPerson.name = ''
    await searchPersons()
  } catch (err) {
    personError.value = err instanceof Error ? err.message : '新建人员失败'
  } finally {
    creatingPerson.value = false
  }
}

async function savePersons() {
  if (!asset.value) return
  personSaving.value = true
  personError.value = ''
  try {
    await api.updateAsset(asset.value.id, {
      persons: selectedPersons.value.map((person, index) => ({
        person_id: person.id,
        role: person.person_type,
        seq: index,
      })),
    })
    toast.success('已保存关联')
    showPersonDrawer.value = false
    await load()
  } catch (err) {
    personError.value = err instanceof Error ? err.message : '保存关联失败'
  } finally {
    personSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <p v-if="loading" class="hint">加载中…</p>
    <p v-else-if="error" class="error-text">{{ error }}</p>

    <template v-else-if="asset">
      <section class="detail-hero">
        <div>
          <span class="badge" style="background: rgba(255,255,255,.16); color: #fff">{{ statusLabels[asset.status_group] }}</span>
          <h1 style="margin-top: 10px">{{ asset.name }}</h1>
          <div class="detail-meta">
            <span v-if="asset.docket_no">我方文号 {{ asset.docket_no }}</span>
            <span>{{ typeLabels[asset.ip_type] }}</span>
            <span>更新于 {{ formatDate(asset.updated_at) }}</span>
          </div>
        </div>
        <RouterLink
          to="/assets"
          class="button ghost"
          style="color:#fff;border-color:rgba(255,255,255,.4)"
        >
          ← 返回列表
        </RouterLink>
      </section>

      <div class="tabs">
        <button class="tab" :class="{ active: tab === 'overview' }" @click="switchTab('overview')">概览</button>
        <button v-if="canAdmin" class="tab" :class="{ active: tab === 'audit' }" @click="switchTab('audit')">操作记录</button>
      </div>

      <template v-if="tab === 'overview'">
      <section class="detail-sections">
        <article class="panel">
          <h2 class="section-heading">基本信息</h2>
          <div class="info-grid two-col">
            <div class="info-item"><label>案件名称</label><span>{{ asset.name }}</span></div>
            <div class="info-item"><label>我方文号</label><span>{{ asset.docket_no || '—' }}</span></div>
            <div class="info-item"><label>知识产权类型</label><span>{{ typeLabels[asset.ip_type] }}</span></div>
            <div class="info-item"><label>综合状态</label><span>{{ statusLabels[asset.status_group] }}</span></div>
            <div class="info-item"><label>创建时间</label><span>{{ formatDate(asset.created_at) }}</span></div>
            <div v-if="asset.ip_type !== 'copyright'" class="info-item full-row"><label>备注</label><span>{{ asset.remark || '—' }}</span></div>
          </div>
        </article>

        <article class="panel">
          <div class="panel-head">
            <h2 class="section-heading">
              {{ asset.ip_type === 'patent' ? '专利信息' : asset.ip_type === 'copyright' ? '软著信息' : '商标信息' }}
            </h2>
            <button v-if="canWrite" class="button ghost small" @click="showEdit = true">编辑</button>
          </div>
          <p v-if="!hasProfessional" class="empty" style="padding: 24px 0">暂未录入专业信息</p>
          <div v-else class="info-grid two-col">
            <div v-for="row in professionalRows" :key="row.key" class="info-item">
              <label>{{ row.label }}</label>
              <span>{{ row.value }}</span>
            </div>
          </div>
        </article>

        <article class="panel">
          <h2 class="section-heading">权利人与人员</h2>
          <div class="sub-heading">权利人</div>
          <p v-if="asset.parties.length === 0" class="hint">尚未关联权利人</p>
          <div v-for="party in asset.parties" :key="party.id" class="person-line">
            <span>{{ party.name }}</span>
            <span class="badge gray">{{ partyTypeLabels[party.party_type] ?? party.party_type }}</span>
          </div>

          <div class="sub-heading-row">
            <div class="sub-heading">人员</div>
            <button v-if="canWrite" class="button ghost small" @click="openPersonDrawer">关联人员</button>
          </div>
          <p v-if="asset.persons.length === 0" class="hint">尚未关联人员</p>
          <div v-for="person in asset.persons" :key="person.id" class="person-line">
            <span>{{ person.name }}</span>
            <span class="badge gray">{{ personTypeLabels[person.person_type] ?? person.person_type }}</span>
          </div>
        </article>

        <article class="panel">
          <h2 class="section-heading">相关记录</h2>
          <p class="hint" style="margin-top: 0">点击后进入对应列表，并自动只看该案件。</p>
          <div class="related-grid">
            <RouterLink v-for="link in relatedLinks" :key="link.to" :to="link.to" class="related-card">
              <strong>{{ link.title }}</strong>
              <small>{{ link.desc }}</small>
            </RouterLink>
          </div>
        </article>
      </section>

      <div v-if="showPersonDrawer">
        <div class="drawer-backdrop" @click="closePersonDrawer"></div>
        <aside class="drawer" role="dialog" aria-modal="true" aria-label="关联人员" tabindex="-1" @keydown.esc="closePersonDrawer">
          <header>
            <small>权利人与人员</small>
            <h2>关联人员</h2>
          </header>
          <div class="drawer-body">
            <div class="sub-heading" style="margin-top: 0">已关联人员</div>
            <p v-if="selectedPersons.length === 0" class="hint">尚未关联人员</p>
            <div v-for="person in selectedPersons" :key="person.id" class="person-pick">
              <span class="person-pick-name">{{ person.name }}</span>
              <span class="badge gray">{{ personTypeLabels[person.person_type] ?? person.person_type }}</span>
              <button class="button ghost small" @click="removePerson(person.id)">取消关联</button>
            </div>

            <div class="sub-heading" style="margin-top: 18px">从已有人员中选择</div>
            <div class="toolbar" style="margin: 0 0 8px">
              <input v-model="personSearch" class="field" placeholder="搜索姓名或工号" @keyup.enter="searchPersons" />
              <button class="button small" :disabled="personLoading" @click="searchPersons">搜索</button>
            </div>
            <p v-if="personLoading" class="hint">加载中…</p>
            <p v-else-if="availablePersons.length === 0" class="hint">没有可关联的人员，可在下方新建。</p>
            <div v-for="person in availablePersons" :key="person.id" class="person-pick">
              <span class="person-pick-name">{{ person.name }}</span>
              <span class="badge gray">{{ personTypeLabels[person.person_type] ?? person.person_type }}</span>
              <button class="button small" @click="addPerson(person)">关联</button>
            </div>

            <div class="sub-heading" style="margin-top: 18px">现场新建人员</div>
            <div class="form-grid">
              <div class="form-item">
                <label for="new_person_name">姓名 *</label>
                <input id="new_person_name" v-model="newPerson.name" placeholder="请输入人员姓名" />
              </div>
              <div class="form-item">
                <label for="new_person_type">人员类型</label>
                <select id="new_person_type" v-model="newPerson.person_type">
                  <option value="inventor">发明人</option>
                  <option value="designer">设计人</option>
                  <option value="developer">开发人员</option>
                  <option value="contact">联系人</option>
                </select>
              </div>
            </div>
            <button class="button small" style="margin-top: 10px" :disabled="creatingPerson" @click="createPerson">
              {{ creatingPerson ? '新建中…' : '新建并关联' }}
            </button>
            <p v-if="personError" class="error-text" style="margin-top: 10px">{{ personError }}</p>
          </div>
          <footer>
            <button class="button ghost" :disabled="personSaving" @click="closePersonDrawer">取消</button>
            <button class="button primary" :disabled="personSaving" @click="savePersons">
              {{ personSaving ? '保存中…' : '保存关联' }}
            </button>
          </footer>
        </aside>
      </div>
      </template>

      <template v-else>
        <div class="panel table-panel">
          <table class="data">
            <thead>
              <tr><th>时间</th><th>动作</th><th>摘要</th><th>IP</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in auditLogs" :key="item.id">
                <td>{{ formatDate(item.created_at) }}</td>
                <td>{{ actionLabels[item.action] ?? item.action }}</td>
                <td>{{ item.summary || '—' }}</td>
                <td>{{ item.ip_address || '—' }}</td>
              </tr>
              <tr v-if="auditLoading"><td colspan="4" class="empty">加载中…</td></tr>
              <tr v-else-if="auditLogs.length === 0"><td colspan="4" class="empty">暂无操作记录</td></tr>
            </tbody>
          </table>
          <div class="pagination">
            <span>共 {{ auditTotal }} 条</span>
            <span>
              <button class="button small" :disabled="auditPage <= 1 || auditLoading" @click="auditPage--; loadAuditLogs()">上一页</button>
              <span style="margin: 0 8px">第 {{ auditPage }} 页</span>
              <button class="button small" :disabled="auditPage * 20 >= auditTotal || auditLoading" @click="auditPage++; loadAuditLogs()">下一页</button>
            </span>
          </div>
        </div>
      </template>

      <AssetFormDrawer
        :open="showEdit"
        :asset-id="asset.id"
        @close="showEdit = false"
        @saved="onEditSaved"
      />
    </template>
  </section>
</template>

<style scoped>
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}
.panel-head .section-heading {
  margin: 0;
  padding: 0;
  border: 0;
}
.sub-heading-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
}
.person-pick {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #eef1f5;
  font-size: 13px;
}
.person-pick-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
