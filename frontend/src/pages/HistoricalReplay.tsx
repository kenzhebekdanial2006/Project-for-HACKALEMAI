import { useI18n } from '../i18n/I18nContext'
import { useEffect, useRef, useState } from 'react'
import { Check, Clock3, History, LoaderCircle, Play, ShieldCheck } from 'lucide-react'
import { Panel, PanelHeading, Badge } from '../components/ui/shared'
import { Button } from '../components/ui/button'
import { ForecastChart } from '../components/charts/ForecastChart'
import { replayService } from '../services/api'
import { useOperations } from '../state/OperationsContext'
import type { ReplayResult } from '../types/forecast'
import { timeLabel } from '../lib/utils'
export default function HistoricalReplay() {
  const { t: translateText, tx, dateLabel, date: formatDate } = useI18n()

  const { diagnostics } = useOperations()
  const [date, setDate] = useState('2026-02-03')
  const [time, setTime] = useState('08:00')
  const [result, setResult] = useState<ReplayResult | null>(null)
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [error, setError] = useState('')
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  const run = async () => {
    if (!date || !time) {
      setError('Choose a date and time from the available weather archive.')
      return
    }
    setRunning(true)
    setError('')
    setLogs([])
    setResult(null)
    try {
      const replay = await replayService.run(date, time)
      if (mounted.current) {
        setResult(replay)
        setLogs(replay.logs)
      }
    } catch (error) {
      if (mounted.current)
        setError(
          error instanceof Error
            ? error.message
            : 'The replay could not be completed. Check the selected date and try again.',
        )
    } finally {
      if (mounted.current) setRunning(false)
    }
  }
  const selectedDate = new Date(`${date || '2026-02-03'}T${time || '08:00'}:00Z`)
  const daysInMonth = new Date(
    Date.UTC(selectedDate.getUTCFullYear(), selectedDate.getUTCMonth() + 1, 0),
  ).getUTCDate()
  const changeDate = (value: string) => {
    setDate(value)
    setResult(null)
    setLogs([])
  }
  return (
    <div className="space-y-5">
      <Panel className="time-machine">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="time-machine-icon">
              <History size={24} />
            </div>
            <div>
              <p className="text-[10px] tracking-[.2em] text-emerald-300">{translateText('TIME MACHINE')}</p>
              <h2 className="mt-1 text-lg">{translateText('A past moment. A fresh perspective.')}</h2>
            </div>
          </div>
          <Badge tone="blue">{translateText('POINT-IN-TIME REPLAY')}</Badge>
        </div>
        <div className="replay-controls">
          <label>
            {translateText('Forecast date')}
            <input
              type="date"
              value={date}
              max={diagnostics?.archiveEnd.slice(0, 10)}
              min={diagnostics?.archiveStart.slice(0, 10)}
              disabled={running}
              onChange={(e) => changeDate(e.target.value)}
            />
          </label>
          <label>
            {translateText('Origin time · UTC')}
            <input
              type="time"
              value={time}
              disabled={running}
              onChange={(e) => {
                setTime(e.target.value)
                setResult(null)
                setLogs([])
              }}
            />
          </label>
          <Button disabled={running || !date || !time} onClick={() => void run()}>
            {tx(running ? <LoaderCircle size={15} className="animate-spin" /> : <Play size={15} />)}
            {tx(running ? 'Running replay…' : 'Run Historical Forecast')}
          </Button>
        </div>
        {tx(
          error && (
            <p className="mt-4 text-sm text-amber-300" role="alert">
              {tx(error)}
            </p>
          ),
        )}
        <div className="mt-8">
          <input
            className="replay-slider"
            aria-label={translateText('Historical day')}
            type="range"
            min={1}
            max={daysInMonth}
            value={selectedDate.getUTCDate()}
            disabled={running || !date}
            onChange={(e) => changeDate(`${date.slice(0, 7)}-${String(e.target.value).padStart(2, '0')}`)}
          />
          <div className="mt-2 flex justify-between text-[10px] text-muted">
            {tx(
              [1, 7, 14, 21, daysInMonth].map((day) => (
                <span key={day}>
                  {formatDate(selectedDate, { month: 'short' })} {tx(day)}
                </span>
              )),
            )}
          </div>
        </div>
      </Panel>
      <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
        <Panel className="historical-mode p-6">
          <div className="mb-6 flex items-center gap-2 text-xs text-sky-300">
            <Clock3 size={15} />
            {translateText('HISTORICAL MODE')}
          </div>
          <p className="font-mono text-3xl tracking-tight">
            {tx(
              formatDate(selectedDate, {
                day: '2-digit',
                month: 'short',
                year: 'numeric',
                timeZone: 'UTC',
              }).toUpperCase(),
            )}
          </p>
          <p className="mt-2 font-mono text-2xl text-muted">
            {tx(time || '08:00')} <span className="text-sm">{translateText('UTC')}</span>
          </p>
          <p className="mt-6 text-xs leading-6 text-muted">
            {translateText(
              'The model training cutoff and archived weather availability policy are checked before calculation.',
            )}
          </p>
          <div className="mt-5 border-t border-white/10 pt-5">
            {tx(
              result ? (
                <Badge tone={result.leakageCheck ? 'green' : 'amber'}>
                  <ShieldCheck size={12} />
                  {tx(result.leakageCheck ? 'INPUT CUTOFF CHECK PASSED ✓' : 'ISSUE TIME REQUIRES REVIEW')}
                </Badge>
              ) : (
                <span className="text-xs text-muted">
                  {translateText('Run replay to validate the forecast origin.')}
                </span>
              ),
            )}
          </div>
          <p className="mt-4 text-[10px] leading-5 text-muted">
            {translateText(
              'Weather availability is estimated as run initialization plus 6 hours 10 minutes. It is not a verified publication timestamp.',
            )}
          </p>
        </Panel>
        <Panel>
          <PanelHeading
            title={translateText('Replay provenance')}
            subtitle={translateText('A transparent record of what was available')}
          />
          <div className="grid gap-x-8 gap-y-5 px-5 pb-6 sm:grid-cols-2">
            {tx(
              [
                [
                  'Forecast origin',
                  `${dateLabel(selectedDate.toISOString())} ${selectedDate.getUTCFullYear()} · ${time}`,
                ],
                [
                  'Weather availability (estimated)',
                  result
                    ? `${dateLabel(result.weatherAvailableAt)} · ${timeLabel(result.weatherAvailableAt)} UTC`
                    : 'Pending replay',
                ],
                ['Forecast horizon', '48 hours'],
                ['Weather source', 'Historical Forecast Archive'],
                ['Model', result?.forecast.modelVersion || diagnostics?.modelVersion || '—'],
                [
                  'Data leakage check',
                  result ? (result.leakageCheck ? 'PASSED' : 'NOT PASSED') : 'Not yet checked',
                ],
              ].map(([label, value]) => (
                <div key={label}>
                  <p className="text-[11px] text-muted">{tx(label)}</p>
                  <p className={`mt-2 text-sm ${value === 'PASSED' ? 'text-emerald-300' : ''}`}>
                    {tx(value)}
                  </p>
                </div>
              )),
            )}
          </div>
        </Panel>
      </div>
      {tx(
        logs.length > 0 && (
          <Panel>
            <PanelHeading
              title={translateText('Replay execution log')}
              action={
                running ? (
                  <Badge tone="blue">{translateText('RUNNING')}</Badge>
                ) : (
                  <Badge>{translateText('COMPLETED')}</Badge>
                )
              }
            />
            <div className="space-y-3 px-5 pb-5" role="log" aria-live="polite">
              {tx(
                logs.map((log, i) => (
                  <div key={log} className="flex items-center gap-3 font-mono text-xs">
                    <span className="text-[#546672]">0{tx(i + 1)}</span>
                    {tx(
                      running && i === logs.length - 1 ? (
                        <LoaderCircle size={12} className="animate-spin text-sky-300" />
                      ) : (
                        <Check size={12} className="text-emerald-300" />
                      ),
                    )}
                    <span className="text-muted">{tx(log)}</span>
                  </div>
                )),
              )}
            </div>
          </Panel>
        ),
      )}
      {tx(
        result ? (
          <Panel>
            <PanelHeading
              title={translateText('Historical 48-hour prediction')}
              subtitle={translateText(
                `Forecast issued from ${dateLabel(result.origin)} · ${timeLabel(result.origin)} UTC`,
              )}
              action={<Badge tone="blue">{translateText('ARCHIVE REPLAY')}</Badge>}
            />
            <div className="p-5">
              <ForecastChart records={result.forecast.records} height={290} historical />
            </div>
          </Panel>
        ) : (
          !running && (
            <div className="replay-empty">
              <History size={28} strokeWidth={1.2} />
              <p>{translateText('Choose a moment. Recreate the forecast.')}</p>
              <span>{translateText('Your historical prediction will appear here.')}</span>
            </div>
          )
        ),
      )}
    </div>
  )
}
