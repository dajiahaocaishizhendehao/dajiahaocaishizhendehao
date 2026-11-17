<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, setToken } from '../api'
import { useAuth } from '../auth'

const router = useRouter()
const { setCurrentUser } = useAuth()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  if (!username.value || !password.value) {
    error.value = '请输入账号和密码'
    return
  }
  loading.value = true
  try {
    const result = await api.login(username.value, password.value)
    setToken(result.access_token)
    setCurrentUser(result.user)
    router.push({ name: 'dashboard' })
  } catch (err) {
    error.value = err instanceof Error ? err.message : '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <form class="login-card" @submit.prevent="submit">
    <h1>知识产权管理系统</h1>
    <p>专利 · 软件著作权 · 商标 / Logo</p>
    <div class="form-item" style="margin-bottom: 14px">
      <label for="username">账号</label>
      <input id="username" v-model="username" autocomplete="username" placeholder="请输入账号" />
    </div>
    <div class="form-item" style="margin-bottom: 18px">
      <label for="password">密码</label>
      <input id="password" v-model="password" type="password" autocomplete="current-password" placeholder="请输入密码" />
    </div>
    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <button class="button primary" style="width: 100%; height: 40px" :disabled="loading">
      {{ loading ? '登录中…' : '登录' }}
    </button>
  </form>
</template>
