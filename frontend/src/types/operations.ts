import type { AgentEvent, AgentStatus } from './agent'
import type { AppNotification, ForecastResponse } from './forecast'
import type { Anomaly, Observation, Turbine } from './turbine'
import type { TelemetrySnapshot } from './telemetry'
export interface ValidationMetrics {
  MAE: number
  RMSE: number
  R2: number
}
export interface DiagnosticsData {
  modelVersion: string
  modelType: string
  modelFingerprint: string
  features: number
  trainingRows: number
  decisionRuns: number
  trainingStart: string
  trainingEnd: string
  validationStart: string
  metrics: ValidationMetrics
  turbineMetrics: Record<string, ValidationMetrics>
  datasets: {
    id: string
    records: number
    hourlyRecords: number
    start: string
    end: string
    lastObservation: Observation
  }[]
  archiveRuns: number
  archiveStart: string
  archiveEnd: string
  telemetryAvailable: boolean
  llmConfigured: boolean
  llmProvider: 'OpenAI' | 'NVIDIA' | null
  llmModel: string | null
  intervalErrors: Record<string, number>
  refreshSeconds: number
}
export interface OperationsSnapshot {
  telemetry: TelemetrySnapshot | null
  forecast: ForecastResponse | null
  turbines: Turbine[]
  anomalies: Anomaly[]
  events: AgentEvent[]
  agent: AgentStatus
  notifications: AppNotification[]
  diagnostics: DiagnosticsData | null
  busy: boolean
  error: string | null
  connected: boolean
  serverTime: string
  nextCheck: string
}
