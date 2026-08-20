/** 与后端 Pydantic 契约对齐的类型定义 */

export type DroneStatus = 'idle' | 'flying' | 'maintenance' | 'offline'
export type UserRole = 'viewer' | 'operator' | 'admin'

export interface TokenResponse {
  access_token: string
  token_type: string
  username: string
  role: UserRole
}

export interface Drone {
  id: number
  name: string
  model: string
  status: DroneStatus
  max_battery_mah: number
  created_at: string
}

export interface DronePage {
  items: Drone[]
  total: number
  page: number
  page_size: number
}

export interface DroneCreateInput {
  name: string
  model: string
  status: DroneStatus
  max_battery_mah: number
}

export type DroneUpdateInput = Partial<DroneCreateInput>

/** 模拟器上行/WS 下行的传感器帧（20 维） */
export interface SensorFrame {
  type: 'sensor_frame'
  drone_id: number
  timestamp: string
  voltage_v: number
  current_a: number
  battery_temp_c: number
  motor_temp_c: number
  ambient_temp_c: number
  spin_thermal_power_w: number
  spin_thermal_voltage_mv: number
  magnetic_x: number
  magnetic_y: number
  magnetic_z: number
  wind_speed_ms: number
  wind_direction_deg: number
  altitude_m: number
  pitch_deg: number
  yaw_deg: number
  roll_deg: number
  gps_lat: number
  gps_lng: number
  battery_soc_percent: number
  fault_code: number
}

/** WS 下行消息：传感器帧或服务端心跳 */
export type WsMessage = { type: 'ping'; ts: number } | { type: 'sensor_frame' } & Record<string, unknown>
