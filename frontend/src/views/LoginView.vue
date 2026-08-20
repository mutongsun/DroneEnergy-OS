<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const form = reactive({ username: '', password: '' })
const loading = ref(false)

async function onSubmit(): Promise<void> {
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/monitor'
    router.push(redirect)
  } catch (err) {
    const detail = err instanceof Error ? err.message : '网络错误'
    ElMessage.error(`登录失败：${detail}`)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="title">
        DroneEnergy-OS
      </h2>
      <p class="subtitle">
        无人机热电监控平台
      </p>
      <el-form
        :model="form"
        @submit.prevent="onSubmit"
      >
        <el-form-item>
          <el-input
            v-model="form.username"
            placeholder="用户名"
            :prefix-icon="User"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-button
          type="primary"
          class="submit"
          :loading="loading"
          native-type="submit"
        >
          登 录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2d3d 0%, #2b4a6f 100%);
}
.login-card {
  width: 380px;
  padding: 12px 8px;
}
.title {
  margin: 4px 0 2px;
  text-align: center;
}
.subtitle {
  margin: 0 0 20px;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
.submit {
  width: 100%;
}
</style>
