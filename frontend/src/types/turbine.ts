import type { MeasurementState, TelemetryMeasurement } from './telemetry'

export interface Observation {
  timestamp: string
  power: number
  wind: number
  temperature: number
}
export interface Turbine {
  id: 'WT-01' | 'WT-02'
  name: string
  wind: number
  direction: number
  temperature: number
  expected: number
  forecastAt: string
  observed: number | null
  observedAt: string | null
  telemetryState: MeasurementState
  measurement: TelemetryMeasurement | null
  confidence: number
  status: 'normal' | 'deviation' | 'unknown'
  lastObservation: Observation | null
}
export interface Anomaly {
  id: string
  date: string
  turbine: string
  title: string
  duration: string
  active: boolean
  end?: string
}
