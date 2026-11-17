/** 金额字符串与整数分之间转换，避免浮点累加误差。 */
export function moneyToCents(value: string | null | undefined): number {
  const text = String(value ?? '').trim().replace(/[¥￥,\s]/g, '')
  if (!/^[-+]?\d*(?:\.\d{0,2})?$/.test(text) || text === '' || text === '.' || text === '-' || text === '+') return 0
  const negative = text.startsWith('-')
  const unsigned = text.replace(/^[-+]/, '')
  const [whole = '0', decimal = ''] = unsigned.split('.')
  const cents = Number.parseInt(whole || '0', 10) * 100 + Number.parseInt(decimal.padEnd(2, '0') || '0', 10)
  return negative ? -cents : cents
}

export function centsToMoney(cents: number): string {
  const sign = cents < 0 ? '-' : ''
  const absolute = Math.abs(Math.trunc(cents))
  return `${sign}${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, '0')}`
}

/** 把后端金额（字符串/数字）格式化为固定两位小数，可带币种前缀。 */
export function formatMoney(value: string | number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || value === '') return '—'
  const money = centsToMoney(moneyToCents(String(value)))
  return currency ? `${currency} ${money}` : money
}
