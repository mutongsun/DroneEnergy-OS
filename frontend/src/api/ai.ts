import { http } from './http'

export interface DiagnoseResult {
  drone_id: number
  action: string
  params: Record<string, unknown>
  reason: string
  decision_type: string | null
  confidence: number | null
  fell_back: boolean
}

export async function diagnose(droneId: number, query?: string): Promise<DiagnoseResult> {
  const { data } = await http.post<DiagnoseResult>('/ai/diagnose', {
    drone_id: droneId,
    query: query ?? '当前能源状态是否有风险？',
  })
  return data
}

export interface HistoryPoint {
  record_time: string
  voltage_v: number | null
  current_a: number | null
  battery_temp_c: number | null
  motor_temp_c: number | null
  spin_thermal_power_w: number | null
  altitude_m: number | null
  battery_soc_percent: number | null
  fault_code: number | null
}

export interface HistoryResult {
  drone_id: number
  minutes: number
  points: HistoryPoint[]
}

export async function getHistory(
  droneId: number,
  minutes = 10,
  limit = 600,
): Promise<HistoryResult> {
  const { data } = await http.get<HistoryResult>(`/sensor/history/${droneId}`, {
    params: { minutes, limit },
  })
  return data
}
