import type {
  ForecastExplanationData,
  ForecastRecord,
  ForecastResponse,
  ReplayResult,
} from '../types/forecast'
import type { OperationsSnapshot, DiagnosticsData } from '../types/operations'
import type { AgentEvent, AgentStatus } from '../types/agent'
import type { Anomaly, Turbine } from '../types/turbine'
import type { CopilotHistoryItem, CopilotResponse } from '../types/copilot'

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
  }
}
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init.headers },
      signal: init.signal || AbortSignal.timeout(60000),
    })
  } catch {
    throw new ApiError('Cannot connect to the operations API. Check that the backend is running.', 0)
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown }
    throw new ApiError(
      typeof body.detail === 'string'
        ? body.detail
        : 'The request could not be completed. Check the selected inputs.',
      response.status,
    )
  }
  return response.json() as Promise<T>
}
export const operationsService = {
  getSnapshot: (signal?: AbortSignal) => request<OperationsSnapshot>('/operations', { signal }),
}
export const forecastService = {
  getForecast: () => request<ForecastResponse>('/forecast'),
  refresh: () => request<{ started: boolean; busy: boolean }>('/forecast/refresh', { method: 'POST' }),
}
export const weatherService = {
  getWeather: () => request<Omit<ForecastRecord, 'WT01' | 'WT02'>[]>('/weather'),
}
export const turbineService = { getTurbines: () => request<Turbine[]>('/turbines') }
export const anomalyService = { getAnomalies: () => request<Anomaly[]>('/anomalies') }
export const agentService = {
  getStatus: () => request<AgentStatus>('/agent/status'),
  getHistory: () => request<AgentEvent[]>('/agent/history'),
}
export const diagnosticsService = { getDiagnostics: () => request<DiagnosticsData>('/diagnostics') }
export const explanationService = {
  getExplanation: (record: ForecastRecord, turbine: 'WT01' | 'WT02') => {
    const query = new URLSearchParams({
      forecast_id: record.forecastId,
      timestamp: record.timestamp,
      turbine,
    })
    return request<ForecastExplanationData>(`/forecast/explanation?${query}`)
  },
}
export const replayService = {
  run: (date: string, time: string) =>
    request<ReplayResult>('/replay', { method: 'POST', body: JSON.stringify({ date, time }) }),
}
export const copilotService = {
  ask: (question: string, locale: string, history: CopilotHistoryItem[] = [], forecastId?: string) =>
    request<CopilotResponse>('/copilot', {
      method: 'POST',
      body: JSON.stringify({ question, locale, history, forecastId }),
    }),
}
