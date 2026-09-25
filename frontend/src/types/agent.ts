export type AgentStage =
  'Weather' | 'Validation' | 'Feature Preparation' | 'Forecast' | 'Twin Analysis' | 'Decision' | 'Publish'
export interface AgentEvent {
  id: string
  time: string
  title: string
  detail: string
  status: 'completed' | 'running' | 'warning'
  stage: AgentStage
}
export interface AgentStatus {
  active: boolean
  task: string
  state: 'Monitoring' | 'Recovering' | 'Processing' | 'Waiting'
  stage: AgentStage | null
  source: 'Primary' | 'Previous run' | 'Cached' | 'Archive' | 'Unavailable'
}
