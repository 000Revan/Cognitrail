export interface LiveHealth {
  service: string
  status: 'alive'
  checkedAt: string
}

export interface ReadyHealth {
  status: 'ready'
  database: 'connected'
  databaseVersion: string
  migrationRevision: string
  timezone: string
  checkedAt: string
}

export type CheckStatus = 'idle' | 'checking' | 'success' | 'error'
export interface CheckResult {
  status: CheckStatus
  message: string
  requestId?: string
}
