<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { diagnose } from '@/api/ai'
import type { DiagnoseResult } from '@/api/ai'

const props = defineProps<{ droneId: number | null }>()

const query = ref('当前能源状态是否有风险？')
const loading = ref(false)
const result = ref<DiagnoseResult | null>(null)

const decisionLabel: Record<string, string> = {
  power_alloc: '能源分配',
  fault_warn: '故障预警',
  route_optimize: '航线优化',
}

async function onDiagnose(): Promise<void> {
  if (props.droneId === null) {
    ElMessage.warning('请先选择无人机')
    return
  }
  loading.value = true
  result.value = null
  try {
    result.value = await diagnose(props.droneId, query.value)
  } catch (err) {
    const detail = err instanceof Error ? err.message : '请求失败'
    ElMessage.error(`诊断失败：${detail}`)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="ai-panel">
    <template #header>
      <div class="header">
        <span>AI 能源诊断（DeepSeek）</span>
        <el-tag v-if="result?.fell_back" type="warning" size="small">本地降级</el-tag>
      </div>
    </template>

    <el-input
      v-model="query"
      type="textarea"
      :rows="2"
      maxlength="500"
      placeholder="向 AI 提问，例如：SOC 下降过快怎么办？"
      class="query"
    />
    <el-button
      type="primary"
      :icon="MagicStick"
      :loading="loading"
      :disabled="droneId === null"
      class="submit"
      @click="onDiagnose"
    >
      {{ loading ? '分析中…' : '开始诊断' }}
    </el-button>

    <div v-if="result" class="result">
      <div class="row">
        <el-tag :type="result.fell_back ? 'warning' : 'success'">
          {{ decisionLabel[result.decision_type ?? ''] ?? result.decision_type }}
        </el-tag>
        <el-tag v-if="result.confidence !== null" type="info">
          置信度 {{ (result.confidence * 100).toFixed(0) }}%
        </el-tag>
        <code class="action">{{ result.action }}</code>
      </div>
      <p class="reason">{{ result.reason }}</p>
      <pre v-if="Object.keys(result.params).length > 0" class="params">{{ result.params }}</pre>
    </div>
    <el-empty v-else-if="!loading" description="选择无人机后发起诊断" :image-size="60" />
  </el-card>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.query {
  margin-bottom: 12px;
}
.submit {
  width: 100%;
}
.result {
  margin-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.action {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.reason {
  margin: 10px 0 0;
  line-height: 1.6;
  font-size: 14px;
}
.params {
  margin: 10px 0 0;
  padding: 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
}
</style>
