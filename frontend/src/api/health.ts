import type { ApiResponse } from '../types/common'
import type { LiveHealth, ReadyHealth } from '../types/health'
import { http } from './http'

export async function getLiveHealth(): Promise<LiveHealth> {
  const response = await http.get<ApiResponse<LiveHealth>>('/health/live')
  return response.data.data
}

export async function getReadyHealth(): Promise<ReadyHealth> {
  const response = await http.get<ApiResponse<ReadyHealth>>('/health/ready')
  return response.data.data
}
