/** 数据库 BIGINT 一律用字符串传递。 */
export type EntityId = string

export interface ApiResponse<T> {
  code: number
  msg: string
  data: T
}

export interface ErrorData {
  errorCode: string
  details: unknown
  requestId: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}
