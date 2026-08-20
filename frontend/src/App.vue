<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Monitor, Platform, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 登录页不套主框架布局
const isLogin = computed(() => route.name === 'login')

function onLogout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <router-view v-if="isLogin" />

  <el-container
    v-else
    class="layout"
  >
    <el-header class="layout-header">
      <div class="brand">
        <el-icon :size="22">
          <Platform />
        </el-icon>
        <span>DroneEnergy-OS 无人机热电监控</span>
      </div>
      <el-menu
        mode="horizontal"
        router
        :default-active="route.path"
        class="nav"
      >
        <el-menu-item index="/monitor">
          <el-icon><Monitor /></el-icon>实时监控
        </el-menu-item>
        <el-menu-item index="/drones">
          <el-icon><Platform /></el-icon>设备管理
        </el-menu-item>
      </el-menu>
      <div class="user-box">
        <span class="username">{{ auth.username }}（{{ auth.role }}）</span>
        <el-button
          :icon="SwitchButton"
          text
          @click="onLogout"
        >
          退出
        </el-button>
      </div>
    </el-header>
    <el-main class="layout-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}
.layout-header {
  display: flex;
  align-items: center;
  gap: 24px;
  border-bottom: 1px solid var(--el-border-color-light);
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  white-space: nowrap;
}
.nav {
  flex: 1;
  border-bottom: none;
}
.user-box {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.username {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
</style>
