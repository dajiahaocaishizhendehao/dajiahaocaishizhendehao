import { describe, expect, it } from 'vitest'
import { centsToMoney, formatMoney, moneyToCents } from './money'

describe('moneyToCents', () => {
  it('解析两位小数金额为分', () => {
    expect(moneyToCents('4500.00')).toBe(450000)
    expect(moneyToCents('4500.5')).toBe(450050)
    expect(moneyToCents('0.01')).toBe(1)
  })

  it('忽略千分位与货币符号', () => {
    expect(moneyToCents('¥1,234.56')).toBe(123456)
  })

  it('空值与非法输入返回 0', () => {
    expect(moneyToCents('')).toBe(0)
    expect(moneyToCents(null)).toBe(0)
    expect(moneyToCents('abc')).toBe(0)
  })

  it('支持负数', () => {
    expect(moneyToCents('-1.50')).toBe(-150)
  })
})

describe('centsToMoney', () => {
  it('固定两位小数', () => {
    expect(centsToMoney(450000)).toBe('4500.00')
    expect(centsToMoney(1)).toBe('0.01')
    expect(centsToMoney(-150)).toBe('-1.50')
  })
})

describe('formatMoney', () => {
  it('空值显示占位符', () => {
    expect(formatMoney(null)).toBe('—')
    expect(formatMoney('')).toBe('—')
  })

  it('带币种前缀并保留两位小数', () => {
    expect(formatMoney('4500', 'CNY')).toBe('CNY 4500.00')
    expect(formatMoney('100.5', 'CNY')).toBe('CNY 100.50')
  })
})
