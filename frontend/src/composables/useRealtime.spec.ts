import { describe, expect, it } from 'vitest'
import { FrameBuffer, parseWsMessage } from './useRealtime'
import type { SensorFrame } from '@/types/api'

function makeFrame(ts: string, voltage = 22.1): SensorFrame {
  return {
    type: 'sensor_frame',
    drone_id: 1,
    timestamp: ts,
    voltage_v: voltage,
    current_a: 10,
    battery_temp_c: 30,
    motor_temp_c: 45,
    ambient_temp_c: 22,
    spin_thermal_power_w: 12,
    spin_thermal_voltage_mv: 20,
    magnetic_x: 0,
    magnetic_y: 0,
    magnetic_z: 250,
    wind_speed_ms: 3,
    wind_direction_deg: 180,
    altitude_m: 100,
    pitch_deg: 0,
    yaw_deg: 0,
    roll_deg: 0,
    gps_lat: 39.9,
    gps_lng: 116.4,
    battery_soc_percent: 88,
    fault_code: 0,
  }
}

describe('parseWsMessage', () => {
  it('解析 sensor_frame', () => {
    const frame = makeFrame('2026-01-01T00:00:00Z')
    expect(parseWsMessage(JSON.stringify(frame))).toEqual(frame)
  })

  it('心跳 ping 返回 null', () => {
    expect(parseWsMessage(JSON.stringify({ type: 'ping', ts: 1 }))).toBeNull()
  })

  it('非 JSON 与非对象返回 null', () => {
    expect(parseWsMessage('not-json')).toBeNull()
    expect(parseWsMessage('42')).toBeNull()
    expect(parseWsMessage('null')).toBeNull()
  })
})

describe('FrameBuffer', () => {
  it('超出窗口丢弃最旧帧', () => {
    const buf = new FrameBuffer(3)
    for (let i = 0; i < 5; i++) {
      buf.push(makeFrame(`t${i}`, i))
    }
    const all = buf.all()
    expect(all).toHaveLength(3)
    expect(all.map((p) => p.voltage_v)).toEqual([2, 3, 4])
  })

  it('clear 清空缓冲', () => {
    const buf = new FrameBuffer(3)
    buf.push(makeFrame('t0'))
    buf.clear()
    expect(buf.all()).toHaveLength(0)
  })
})
