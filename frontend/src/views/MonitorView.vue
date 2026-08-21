<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { EChartsOption } from 'echarts'
import RealtimeChart from '@/components/RealtimeChart.vue'
import Drone3D from '@/components/Drone3D.vue'
import AiPanel from '@/components/AiPanel.vue'
import { useRealtime } from '@/composables/useRealtime'
import { listDrones } from '@/api/drones'
import type { Drone } from '@/types/api'

const drones = ref<Drone[]>([])
const selectedId = ref<number | null>(null)
const { connected, latest, series, connect, disconnect } = useRealtime(120)

onMounted(async () => {
  try {
    const page = await listDrones({ page: 1, page_size: 100 })
    drones.value = page.items
    selectedId.value = page.items.length > 0 ? page.items[0]!.id : null
  } catch {
    ElMessage.error('无人机列表加载失败')
  }
})

watch(selectedId, (id) => {
  if (id !== null) {
    connect(id)
  } else {
    disconnect()
  }
})

// ---------- 指标卡片 ----------
const metrics = computed(() => {
  const f = latest.value
  return [
    { label: '电压 (V)', value: f?.voltage_v },
    { label: '电流 (A)', value: f?.current_a },
    { label: '电池 SOC (%)', value: f?.battery_soc_percent },
    { label: '电池温度 (°C)', value: f?.battery_temp_c },
    { label: '电机温度 (°C)', value: f?.motor_temp_c },
    { label: '热电功率 (W)', value: f?.spin_thermal_power_w },
    { label: '风速 (m/s)', value: f?.wind_speed_ms },
    { label: '故障码', value: f?.fault_code },
  ]
})

// ---------- 实时曲线 ----------
const chartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['电压 (V)', '电流 (A)', '电池 SOC (%)'] },
  grid: { left: 48, right: 48, top: 40, bottom: 32 },
  xAxis: {
    type: 'category',
    data: series.value.map((p) => p.ts.slice(11, 19)), // HH:MM:SS
    axisLabel: { rotate: 30 },
  },
  yAxis: [
    { type: 'value', name: '电压/电流', scale: true },
    { type: 'value', name: 'SOC %', min: 0, max: 100 },
  ],
  series: [
    { name: '电压 (V)', type: 'line', showSymbol: false, data: series.value.map((p) => p.voltage_v) },
    { name: '电流 (A)', type: 'line', showSymbol: false, data: series.value.map((p) => p.current_a) },
    {
      name: '电池 SOC (%)',
      type: 'line',
      showSymbol: false,
      yAxisIndex: 1,
      data: series.value.map((p) => p.battery_soc_percent),
    },
  ],
}))
</script>

<template>
  <div class="monitor">
    <div class="toolbar">
      <el-select
        v-model="selectedId"
        placeholder="选择无人机"
        class="drone-select"
        :disabled="drones.length === 0"
      >
        <el-option
          v-for="d in drones"
          :key="d.id"
          :label="`${d.name}（${d.model}）`"
          :value="d.id"
        />
      </el-select>
      <el-tag
        :type="connected ? 'success' : 'info'"
        effect="dark"
      >
        {{ connected ? '实时连接中' : '未连接' }}
      </el-tag>
      <el-tag
        v-if="latest?.fault_code"
        type="danger"
        effect="dark"
      >
        故障码 {{ latest.fault_code }}
      </el-tag>
    </div>

    <el-empty
      v-if="drones.length === 0"
      description="暂无无人机，请先在设备管理中录入"
    />

    <template v-else>
      <el-row
        :gutter="12"
        class="metrics"
      >
        <el-col
          v-for="m in metrics"
          :key="m.label"
          :span="6"
          class="metric-col"
        >
          <el-card
            shadow="never"
            class="metric-card"
          >
            <div class="metric-label">
              {{ m.label }}
            </div>
            <div class="metric-value">
              {{ m.value ?? '--' }}
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :span="14">
          <el-card
            shadow="never"
            class="chart-card"
          >
            <template #header>
              实时遥测（最近 120 帧，1Hz ≈ 2 分钟）
            </template>
            <RealtimeChart :option="chartOption" />
          </el-card>
        </el-col>
        <el-col :span="10">
          <el-card
            shadow="never"
            class="chart-card pose-card"
          >
            <template #header>
              3D 姿态（pitch / yaw / roll 实时驱动）
            </template>
            <Drone3D :frame="latest" />
          </el-card>
        </el-col>
      </el-row>

      <AiPanel :drone-id="selectedId" class="ai-row" />
    </template>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.drone-select {
  width: 280px;
}
.metrics {
  margin-bottom: 16px;
}
.metric-col {
  margin-bottom: 12px;
}
.metric-card {
  text-align: center;
}
.metric-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.metric-value {
  font-size: 24px;
  font-weight: 600;
  margin-top: 4px;
}
.chart-card {
  min-height: 380px;
}
.pose-card {
  height: 100%;
}
.ai-row {
  margin-top: 12px;
}
</style>
