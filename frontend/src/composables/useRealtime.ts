import { ref, shallowRef, onBeforeUnmount } from 'vue'
import type { SensorFrame } from '@/types/api'

/** WS 下行解析：sensor_frame 返回帧，ping / 非 JSON / 缺字段返回 null */
export function parseWsMessage(raw: string): SensorFrame | null {
  try {
    const msg: unknown = JSON.parse(raw)
    if (typeof msg !== 'object' || msg === null) return null
    const obj = msg as Record<string, unknown>
    if (obj.type !== 'sensor_frame') return null // 心跳 ping
    return obj as unknown as SensorFrame
  } catch {
    return null
  }
}

export interface FramePoint {
  ts: string
  voltage_v: number
  current_a: number
  battery_soc_percent: number
  spin_thermal_power_w: number
}

/** 滚动窗口缓冲：超过 maxPoints 丢弃最旧帧（实时曲线只看最近 N 秒） */
export class FrameBuffer {
  private points: FramePoint[] = []

  constructor(private readonly maxPoints: number = 120) {}

  push(frame: SensorFrame): void {
    this.points.push({
      ts: frame.timestamp,
      voltage_v: frame.voltage_v,
      current_a: frame.current_a,
      battery_soc_percent: frame.battery_soc_percent,
      spin_thermal_power_w: frame.spin_thermal_power_w,
    })
    if (this.points.length > this.maxPoints) {
      this.points.splice(0, this.points.length - this.maxPoints)
    }
  }

  all(): FramePoint[] {
    return [...this.points]
  }

  clear(): void {
    this.points = []
  }
}

export function wsBaseUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}`
}

/**
 * 实时帧订阅：连接 /ws/realtime/{droneId}，维护最新帧与滚动曲线缓冲。
 * 断线由浏览器 WebSocket 自动兜底（后端心跳 ping 30s 侦测死连接），
 * 本期不做前端自动重连，留待 v2。
 */
export function useRealtime(maxPoints = 120) {
  const connected = ref(false)
  const latest = shallowRef<SensorFrame | null>(null)
  const buffer = new FrameBuffer(maxPoints)
  const series = ref<FramePoint[]>([])
  let ws: WebSocket | null = null

  function connect(droneId: number): void {
    disconnect()
    buffer.clear()
    series.value = []
    latest.value = null
    ws = new WebSocket(`${wsBaseUrl()}/ws/realtime/${droneId}`)
    ws.onopen = () => {
      connected.value = true
    }
    ws.onmessage = (ev: MessageEvent<string>) => {
      const frame = parseWsMessage(ev.data)
      if (frame === null) return
      latest.value = frame
      buffer.push(frame)
      series.value = buffer.all() // 触发响应式更新
    }
    ws.onclose = () => {
      connected.value = false
    }
  }

  function disconnect(): void {
    if (ws !== null) {
      ws.onclose = null // 主动关闭不算"断连"
      ws.close()
      ws = null
    }
    connected.value = false
  }

  onBeforeUnmount(disconnect)

  return { connected, latest, series, connect, disconnect }
}
