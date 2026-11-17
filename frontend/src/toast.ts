import { reactive } from 'vue'

export interface ToastItem {
  id: number
  kind: 'success' | 'error' | 'info'
  message: string
}

const toasts = reactive<ToastItem[]>([])
let seq = 0

function push(kind: ToastItem['kind'], message: string): void {
  const id = ++seq
  toasts.push({ id, kind, message })
  setTimeout(() => {
    const index = toasts.findIndex((item) => item.id === id)
    if (index >= 0) toasts.splice(index, 1)
  }, 4000)
}

/** 全局轻提示：成功/失败/信息。所有视图共用，替代各自的内联 flash。 */
export function useToast() {
  return {
    toasts,
    success: (message: string) => push('success', message),
    error: (message: string) => push('error', message),
    info: (message: string) => push('info', message),
  }
}
