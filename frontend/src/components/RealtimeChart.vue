<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, shallowRef } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{ option: EChartsOption }>()

const el = shallowRef<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function render(): void {
  if (chart !== null) {
    chart.setOption(props.option)
  }
}

function onResize(): void {
  chart?.resize()
}

onMounted(() => {
  if (el.value !== null) {
    chart = echarts.init(el.value)
    render()
    window.addEventListener('resize', onResize)
  }
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div
    ref="el"
    class="chart"
  />
</template>

<style scoped>
.chart {
  width: 100%;
  height: 100%;
  min-height: 300px;
}
</style>
