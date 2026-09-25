export type Page = 'overview' | 'forecast' | 'twin' | 'agent' | 'replay' | 'diagnostics'
export interface PowerForecast {
  prediction: number
  lower: number
  upper: number
  confidence: number
}
export interface ForecastRecord {
  timestamp: string
  forecastId: string
  windSpeed10m: number
  windSpeed80m: number
  windSpeed120m: number
  windDirection: number
  gusts: number
  temperature: number
  pressure: number
  WT01: PowerForecast
  WT02: PowerForecast
}
export interface ConfidenceFactors {
  weatherData: number | null
  modelStability: number | null
  twinConsistency: number | null
  dataFreshness: number | null
  forecastAgreement: number | null
}
export interface ForecastResponse {
  id: string
  records: ForecastRecord[]
  confidence: number
  factors: ConfidenceFactors
  source: string
  sourceState: 'Primary' | 'Previous run' | 'Cached' | 'Archive'
  issuedAt: string
  origin: string
  nextUpdate: string
  mode: 'live' | 'historical'
  weatherRun: string
  weatherAvailableAt: string
  availabilityEstimated: boolean
  modelVersion: string
  modelFingerprint: string
  trainingCutoff: string
  telemetryAvailable: boolean
  intervalMethod: string
  changeSincePrevious: number | null
  stale?: boolean
}
export interface AppNotification {
  id: string
  title: string
  description: string
  severity: 'Info' | 'Warning' | 'Critical'
  time: string
  read: boolean
}
export interface ReplayResult {
  forecast: ForecastResponse
  origin: string
  weatherIssuedAt: string
  weatherAvailableAt: string
  trainingCutoff: string
  leakageCheck: boolean
  availabilityEstimated: boolean
  logs: string[]
}
export interface ForecastExplanationData {
  drivers: { label: string; note: string; value: number; negative: boolean; contribution: number }[]
  historicalCount: number
  historicalAverage: number | null
  historicalLower: number | null
  historicalUpper: number | null
  periods: { timestamp: string; power: number }[]
  method: string
  matchingRule: string
}
