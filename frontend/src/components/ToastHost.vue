<script setup lang="ts">
import { useToast } from '../toast'

const { toasts } = useToast()
</script>

<template>
  <div class="toast-host" aria-live="polite" aria-atomic="false">
    <div v-for="item in toasts" :key="item.id" class="toast" :class="item.kind">
      <span class="toast-icon">{{ item.kind === 'success' ? '✓' : item.kind === 'error' ? '✕' : 'ℹ' }}</span>
      <span>{{ item.message }}</span>
    </div>
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  top: 18px;
  right: 20px;
  z-index: 400;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}
.toast {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 220px;
  max-width: 360px;
  padding: 11px 14px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--line);
  box-shadow: 0 16px 40px rgba(7, 18, 38, 0.18);
  font-size: 13px;
  color: var(--ink);
}
.toast-icon {
  flex: none;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
}
.toast.success .toast-icon {
  background: #e8f7f1;
  color: #16865a;
}
.toast.error .toast-icon {
  background: #fff0f1;
  color: #c44451;
}
.toast.info .toast-icon {
  background: #edf3ff;
  color: #2e68c5;
}
</style>
