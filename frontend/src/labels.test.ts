import { describe, expect, it } from 'vitest'
import {
  formatValidationMessage,
  statusLabels,
  translateErrorType,
  typeLabels,
} from './labels'

describe('标签字典', () => {
  it('核心枚举值都有中文标签', () => {
    expect(typeLabels.patent).toBe('专利')
    expect(typeLabels.copyright).toBe('软件著作权')
    expect(statusLabels.granted).toBe('已取得权利')
  })
})

describe('translateErrorType', () => {
  it('翻译常见 Pydantic 错误类型', () => {
    expect(translateErrorType('missing', '')).toBe('不能为空')
    expect(translateErrorType('greater_than_equal', '')).toBe('数值过小')
    expect(translateErrorType('decimal_max_places', '')).toBe('最多两位小数')
    expect(translateErrorType('enum', '')).toBe('取值无效')
  })

  it('未知类型回退到原始信息', () => {
    expect(translateErrorType('custom_type', '自定义错误')).toBe('自定义错误')
  })
})

describe('formatValidationMessage', () => {
  it('把字段错误拼成可读中文', () => {
    const message = formatValidationMessage({
      amount_due: { type: 'greater_than_equal', msg: 'greater than or equal to 0' },
      name: { type: 'missing', msg: 'Field required' },
    })
    expect(message).toBe('应付金额：数值过小；名称：不能为空')
  })

  it('空字段返回通用提示', () => {
    expect(formatValidationMessage({})).toBe('输入校验失败')
  })
})
