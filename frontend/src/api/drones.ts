import { http } from './http'
import type { Drone, DroneCreateInput, DronePage, DroneUpdateInput } from '@/types/api'

export interface DroneQuery {
  status?: string
  model?: string
  page: number
  page_size: number
}

export async function listDrones(query: DroneQuery): Promise<DronePage> {
  const { data } = await http.get<DronePage>('/drones', { params: query })
  return data
}

export async function createDrone(input: DroneCreateInput): Promise<Drone> {
  const { data } = await http.post<Drone>('/drones', input)
  return data
}

export async function updateDrone(id: number, input: DroneUpdateInput): Promise<Drone> {
  const { data } = await http.patch<Drone>(`/drones/${id}`, input)
  return data
}

export async function deleteDrone(id: number): Promise<void> {
  await http.delete(`/drones/${id}`)
}
