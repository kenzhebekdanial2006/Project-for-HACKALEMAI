export interface TelemetryMeasurement {
  turbineId: 'WT-01' | 'WT-02'
  timestamp: string
  power: number
  windSpeed: number | null
  windDirection: number | null
  temperature: number | null
}

export type MeasurementState = 'fresh' | 'stale' | 'missing' | 'unavailable'

export interface TelemetrySnapshot {
  status: 'not_configured' | 'waiting' | 'connected' | 'partial' | 'stale' | 'error'
  available: boolean
  freshCount: number
  source: 'Telemetry API' | 'CSV file' | 'JSON file'
  maxAgeSeconds: number
  apiEnabled: boolean
  fileConfigured: boolean
  error: string | null
  readings: {
    turbineId: 'WT-01' | 'WT-02'
    state: MeasurementState
    ageSeconds: number | null
    measurement: TelemetryMeasurement | null
  }[]
}

export function telemetryLabel(telemetry: TelemetrySnapshot | null): string {
  if (!telemetry) return 'Checking turbine readings'
  const labels: Record<TelemetrySnapshot['status'], string> = {
    not_configured: 'Current turbine readings are not connected',
    waiting: 'Waiting for turbine readings',
    connected: 'Current turbine readings available',
    partial: 'Some turbine readings are unavailable',
    stale: 'Turbine readings are out of date',
    error: 'Turbine readings need attention',
  }
  return labels[telemetry.status]
}
