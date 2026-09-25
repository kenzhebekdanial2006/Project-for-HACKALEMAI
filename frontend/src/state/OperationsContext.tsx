import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { forecastService, operationsService } from '../services/api'
import type { AppNotification, Page } from '../types/forecast'
import type { OperationsSnapshot } from '../types/operations'
import { timeLabel } from '../lib/utils'

interface OperationsState extends OperationsSnapshot {
  page: Page
  loading: boolean
  lastUpdate: string
  setPage: (page: Page) => void
  refresh: () => Promise<void>
  notify: (title: string, description: string, severity?: AppNotification['severity']) => void
  markRead: () => void
}
const OperationsContext = createContext<OperationsState | null>(null)
const initial: OperationsSnapshot = {
  telemetry: null,
  forecast: null,
  turbines: [],
  anomalies: [],
  events: [],
  diagnostics: null,
  notifications: [],
  busy: false,
  error: null,
  connected: false,
  serverTime: '',
  nextCheck: '',
  agent: {
    active: false,
    state: 'Waiting',
    task: 'Connecting to the operations API',
    stage: null,
    source: 'Unavailable',
  },
}
function pageFromHash(): Page {
  const page = window.location.hash.slice(1)
  return ['overview', 'forecast', 'twin', 'agent', 'replay', 'diagnostics'].includes(page)
    ? (page as Page)
    : 'overview'
}
export function OperationsProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState(initial)
  const [page, updatePage] = useState<Page>(pageFromHash)
  const [loading, setLoading] = useState(true)
  const [localNotifications, setLocalNotifications] = useState<AppNotification[]>([])
  const [readIds, setReadIds] = useState<Set<string>>(new Set())
  const locked = useRef(false)
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    let stopped = false
    let timer: number
    const controller = new AbortController()
    const poll = async () => {
      let busy = false
      try {
        const data = await operationsService.getSnapshot(controller.signal)
        busy = data.busy
        if (!stopped) setSnapshot(data)
      } catch (error) {
        if (!stopped)
          setSnapshot((previous) => ({
            ...previous,
            connected: false,
            busy: false,
            error: error instanceof Error ? error.message : 'Operational data is temporarily unavailable.',
            agent: {
              ...previous.agent,
              active: false,
              state: 'Waiting',
              source: 'Unavailable',
              task: 'Connecting to the operations API',
            },
            telemetry: previous.telemetry
              ? {
                  ...previous.telemetry,
                  available: false,
                  freshCount: 0,
                  status: 'error',
                  error: 'Cannot connect to the operations API. Check that the backend is running.',
                  readings: previous.telemetry.readings.map((reading) => ({
                    ...reading,
                    state: 'unavailable',
                  })),
                }
              : null,
            turbines: previous.turbines.map((turbine) => ({
              ...turbine,
              observed: null,
              observedAt: null,
              telemetryState: 'unavailable',
            })),
            forecast: previous.forecast
              ? { ...previous.forecast, stale: true, telemetryAvailable: false }
              : null,
          }))
      } finally {
        if (!stopped) {
          setLoading(false)
          timer = window.setTimeout(poll, busy ? 1500 : 5000)
        }
      }
    }
    void poll()
    return () => {
      stopped = true
      mounted.current = false
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [])
  const setPage = useCallback((next: Page) => {
    window.location.hash = next
    updatePage(next)
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [])
  useEffect(() => {
    const listener = () => updatePage(pageFromHash())
    window.addEventListener('hashchange', listener)
    return () => window.removeEventListener('hashchange', listener)
  }, [])
  const refresh = useCallback(async () => {
    if (locked.current) return
    locked.current = true
    setSnapshot((previous) => ({ ...previous, busy: true, error: null }))
    try {
      await forecastService.refresh()
      const data = await operationsService.getSnapshot()
      if (mounted.current) setSnapshot(data)
    } catch (error) {
      if (mounted.current)
        setSnapshot((previous) => ({
          ...previous,
          busy: false,
          error: error instanceof Error ? error.message : 'Forecast update unavailable',
        }))
    } finally {
      locked.current = false
    }
  }, [])
  const notify = useCallback(
    (title: string, description: string, severity: AppNotification['severity'] = 'Info') => {
      setLocalNotifications((items) =>
        [
          {
            id: crypto.randomUUID(),
            title,
            description,
            severity,
            time: timeLabel(new Date().toISOString()),
            read: false,
          },
          ...items,
        ].slice(0, 20),
      )
    },
    [],
  )
  const notifications = [...localNotifications, ...snapshot.notifications].map((item) => ({
    ...item,
    read: readIds.has(item.id),
  }))
  return (
    <OperationsContext.Provider
      value={{
        ...snapshot,
        notifications,
        page,
        loading,
        setPage,
        refresh,
        notify,
        lastUpdate: snapshot.forecast ? timeLabel(snapshot.forecast.issuedAt) : '—',
        markRead: () => setReadIds(new Set(notifications.map((item) => item.id))),
      }}
    >
      {children}
    </OperationsContext.Provider>
  )
}
export function useOperations() {
  const context = useContext(OperationsContext)
  if (!context) throw new Error('OperationsProvider is required')
  return context
}
