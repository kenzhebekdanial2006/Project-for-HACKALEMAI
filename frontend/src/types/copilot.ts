export interface CopilotHistoryItem {
  role: 'user' | 'assistant'
  content: string
}

export interface CopilotResponse {
  answer: string
  references: string[]
  provider: 'OpenAI' | 'NVIDIA' | 'Data analysis'
  model: string | null
  forecastId: string
  fallback: boolean
  fallbackReason: string | null
  notice: string | null
}
