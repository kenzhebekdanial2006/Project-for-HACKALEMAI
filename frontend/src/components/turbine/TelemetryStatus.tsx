import { Radio, Clock3 } from 'lucide-react'
import { useOperations } from '../../state/OperationsContext'
import { useI18n } from '../../i18n/I18nContext'
import { telemetryLabel } from '../../types/telemetry'
import { percent, timeLabel } from '../../lib/utils'
import { Badge, Panel, PanelHeading } from '../ui/shared'

export function TelemetryStatus({ setup = false }: { setup?: boolean }) {
  const { telemetry } = useOperations()
  const { t, tx, dateLabel, number } = useI18n()
  const available = telemetry?.available ?? false
  return (
    <Panel>
      <PanelHeading
        title={t('Current turbine readings')}
        icon={<Radio size={17} className={available ? 'text-emerald-300' : 'text-sky-300'} />}
        action={
          <Badge tone={available ? 'green' : 'gray'}>
            {t(available ? 'RECEIVING DATA' : 'CHECK SOURCE')}
          </Badge>
        }
      />
      <div className="space-y-4 px-5 pb-5" data-testid="telemetry-status">
        <div>
          <p className="text-sm font-medium" data-testid="telemetry-summary">
            {t(telemetryLabel(telemetry))}
          </p>
          <p className="mt-2 text-xs leading-6 text-muted">
            {t(
              available
                ? 'Measured power is shown with its timestamp. The forecast covers future hours; turbine operating state still requires verification.'
                : 'Connect measurements from the station or an automatically updated file. Weather forecasts and historical datasets do not contain current turbine output.',
            )}
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {telemetry?.readings.map((reading) => (
            <div
              key={reading.turbineId}
              className="min-w-0 rounded-xl border border-white/10 p-4"
              data-testid={`measurement-${reading.turbineId}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs">{reading.turbineId}</span>
                <Badge
                  tone={reading.state === 'fresh' ? 'green' : reading.state === 'stale' ? 'amber' : 'gray'}
                >
                  {t(
                    reading.state === 'fresh'
                      ? 'FRESH READING'
                      : reading.state === 'stale'
                        ? 'OUT OF DATE'
                        : reading.state === 'unavailable'
                          ? 'UNAVAILABLE'
                          : 'NO READING',
                  )}
                </Badge>
              </div>
              <p className="mt-3 text-2xl">{tx(percent(reading.measurement?.power ?? null))}</p>
              <p className="mt-1 text-[10px] text-muted">
                {t(reading.state === 'fresh' ? 'Observed power' : 'Last received reading')}
              </p>
              {reading.measurement && (
                <p className="mt-3 flex items-start gap-2 text-[11px] leading-5 text-muted">
                  <Clock3 size={13} className="mt-1 shrink-0" />
                  <time>
                    {dateLabel(reading.measurement.timestamp)}{' '}
                    {new Date(reading.measurement.timestamp).getUTCFullYear()} ·{' '}
                    {timeLabel(reading.measurement.timestamp)} UTC
                  </time>
                </p>
              )}
            </div>
          ))}
        </div>
        {telemetry?.error && (
          <p role="status" className="text-xs leading-6 text-amber-300">
            {t(telemetry.error)}
          </p>
        )}
        {telemetry && (
          <p className="text-xs leading-6 text-muted">
            {t('Maximum reading age')}: {number(telemetry.maxAgeSeconds / 60, 0)} {t('minutes')}.{' '}
            {t('Older readings are retained with their timestamp and are not shown as current power.')}
          </p>
        )}
        {setup && (
          <details className="rounded-lg border border-white/10 p-4 text-xs leading-6">
            <summary className="cursor-pointer text-sky-300">{t('How to connect turbine readings')}</summary>
            <p className="mt-3 text-muted">
              {t(
                'Ask the station administrator for measured power, turbine IDs and measurement timestamps. Supply power as a fraction of rated power (0–1), with an explicit timestamp timezone.',
              )}
            </p>
            <p className="mt-3 text-muted">
              {t(
                'File connection: set WINDOPS_TELEMETRY_FILE in backend/.env to the updated CSV or JSON file, then restart the backend.',
              )}
            </p>
            <p className="mt-3 text-muted">
              {t(
                'API connection: set WINDOPS_TELEMETRY_KEY on the backend, then send readings to POST /api/telemetry using the X-Telemetry-Key header. Keep this key on the sending server.',
              )}
            </p>
            <p className="mt-3 text-muted">
              {t(
                'Connection formats and commands are documented in docs/TELEMETRY.md. Restarting the backend is only needed after changing connection settings.',
              )}
            </p>
            {telemetry && (
              <p className="mt-3">
                {t('Source')}: {t(telemetry.source)} ·{' '}
                {t(
                  telemetry.fileConfigured
                    ? 'File connection configured'
                    : telemetry.apiEnabled
                      ? 'API ingestion enabled'
                      : 'Connection not configured',
                )}
              </p>
            )}
          </details>
        )}
      </div>
    </Panel>
  )
}
