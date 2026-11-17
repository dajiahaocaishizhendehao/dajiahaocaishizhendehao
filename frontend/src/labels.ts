/** 共享枚举中文标签与校验错误翻译。
 *
 * 所有视图统一从这里取值，避免各页面复制粘贴导致标签漂移。
 */

export const typeLabels: Record<string, string> = {
  patent: '专利',
  copyright: '软件著作权',
  trademark: '商标 / Logo',
}

export const statusLabels: Record<string, string> = {
  in_progress: '办理中',
  granted: '已取得权利',
  invalid: '已失效',
  other: '其他',
}

export const feeLabels: Record<string, string> = {
  annuity: '年费',
  agency: '代理费',
  application: '申请费',
  substantive: '实审费',
  registration: '登记费',
  material: '材料费',
  other: '其他',
}

export const feeStatusLabels: Record<string, string> = {
  unpaid: '未支付',
  partial: '部分支付',
  paid: '已支付',
  canceled: '已取消',
}

export const dateTypeLabels: Record<string, string> = {
  planned: '计划日期',
  due: '截止日期',
  actual: '实际完成日期',
  custom: '自定义',
}

export const dateSourceLabels: Record<string, string> = {
  manual: '手工录入',
  imported: '数据导入',
  rule: '规则生成',
}

export const dateStatusLabels: Record<string, string> = {
  open: '未完成',
  done: '已完成',
  canceled: '已取消',
}

export const partyTypeLabels: Record<string, string> = {
  company: '企业',
  person: '个人',
  organization: '其他组织',
}

export const personTypeLabels: Record<string, string> = {
  inventor: '发明人',
  designer: '设计人',
  developer: '开发人员',
  contact: '联系人',
}

export const patentTypeLabels: Record<string, string> = {
  invention: '发明专利',
  utility: '实用新型',
  design: '外观设计',
}

export const markTypeLabels: Record<string, string> = {
  word: '文字商标',
  figurative: '图形商标',
  combined: '组合商标',
}

export const materialFlagLabels: Record<string, string> = {
  normal: '普通材料',
  final: '最终版',
  original_scan: '原件扫描件',
}

export const materialCategoryLabels: Record<string, string> = {
  certificate_scan: '证书扫描件',
  application_document: '申请文件',
  official_notice: '官方通知',
  software_manual: '软件说明书',
  logo_image: 'Logo 图样',
  annuity_voucher: '年费缴费凭证',
  invoice: '发票附件',
  other: '其他',
}

export const roleLabels: Record<string, string> = {
  admin: '系统管理员',
  ip_admin: '管理员',
  user: '普通用户',
}

export const reimbursementLabels: Record<string, string> = {
  not_submitted: '未提交',
  pending: '待报销',
  done: '已报销',
}

export const actionLabels: Record<string, string> = {
  create: '新增',
  update: '修改',
  delete: '删除',
  export: '导出',
  import: '导入',
  download_template: '下载模板',
  login: '登录',
  logout: '退出',
  complete: '标记完成',
  upload: '上传',
  extract: '材料识别',
  download: '下载',
  recognize_invoice: '识别发票',
  link_invoice: '关联发票',
  replace_file: '更换文件',
}

// 校验错误里字段名 → 中文标签，用于把 Pydantic 的字段路径翻译成可读提示。
export const fieldLabels: Record<string, string> = {
  name: '名称',
  docket_no: '我方文号',
  ip_type: '知识产权类型',
  status_group: '综合状态',
  fee_type: '费用类型',
  amount_due: '应付金额',
  amount_paid: '实付金额',
  currency: '币种',
  due_date: '应缴日',
  paid_date: '实缴日',
  coverage_end_date: '本次缴费缴至',
  title: '事项名称',
  date_type: '日期类型',
  planned_date: '计划日期',
  actual_date: '实际完成日期',
  invoice_no: '发票号码',
  invoice_code: '发票代码',
  amount_net: '不含税金额',
  tax_amount: '税额',
  amount_gross: '价税合计',
  username: '账号',
  password: '密码',
  display_name: '姓名',
  role: '角色',
  party_type: '权利人类型',
  category: '分类',
  display_name_file: '文件名称',
  application_no: '申请号',
  application_date: '申请日期',
  grant_date: '授权公告日',
  patent_no: '专利号',
  registration_no: '注册号',
}

/** 把 Pydantic 错误类型翻译成简短中文。 */
export function translateErrorType(type: string, msg: string): string {
  switch (type) {
    case 'missing':
      return '不能为空'
    case 'string_too_long':
      return '长度超限'
    case 'string_too_short':
      return '长度不足'
    case 'greater_than_equal':
      return '数值过小'
    case 'less_than_equal':
      return '数值过大'
    case 'decimal_max_places':
      return '最多两位小数'
    case 'decimal_max_digits':
      return '数值过大'
    case 'enum':
      return '取值无效'
    case 'int_parsing':
    case 'decimal_parsing':
    case 'date_parsing':
    case 'string_type':
      return '格式不正确'
    default:
      return msg || '输入无效'
  }
}

/** 把后端统一校验错误 {field: {type,msg}} 拼成一条可读中文。 */
export function formatValidationMessage(
  fields: Record<string, { type: string; msg: string }>,
): string {
  const parts = Object.entries(fields).map(([field, info]) => {
    const label = fieldLabels[field] ?? field
    return `${label}：${translateErrorType(info.type, info.msg)}`
  })
  return parts.join('；') || '输入校验失败'
}
