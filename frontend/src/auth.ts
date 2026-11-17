import { computed, readonly, ref } from 'vue'
import { api, getToken, type User } from './api'

const currentUser = ref<User | null>(null)
const initialized = ref(false)
let loading: Promise<User | null> | null = null

async function loadCurrentUser(force = false): Promise<User | null> {
  if (!getToken()) {
    currentUser.value = null
    initialized.value = true
    return null
  }
  if (initialized.value && !force) return currentUser.value
  if (loading) return loading

  loading = api.me()
    .then((user) => {
      currentUser.value = user
      return user
    })
    .catch(() => {
      currentUser.value = null
      return null
    })
    .finally(() => {
      initialized.value = true
      loading = null
    })
  return loading
}

function setCurrentUser(user: User): void {
  currentUser.value = user
  initialized.value = true
  loading = null
}

function clearCurrentUser(): void {
  currentUser.value = null
  initialized.value = false
  loading = null
}

const canWrite = computed(() => currentUser.value?.role === 'admin' || currentUser.value?.role === 'ip_admin')
const canAdmin = computed(() => currentUser.value?.role === 'admin')

export function useAuth() {
  return {
    currentUser: readonly(currentUser),
    initialized: readonly(initialized),
    canWrite,
    canAdmin,
    loadCurrentUser,
    setCurrentUser,
    clearCurrentUser,
  }
}

export async function ensureAuthLoaded(): Promise<User | null> {
  return loadCurrentUser()
}
