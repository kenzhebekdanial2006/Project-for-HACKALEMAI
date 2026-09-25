import { useI18n } from '../../i18n/I18nContext'
import { ArrowUpRight, Compass, Thermometer, Wind } from 'lucide-react'
import type { Turbine } from '../../types/turbine'
import { percent, timeLabel } from '../../lib/utils'
import { Badge } from '../ui/shared'
import { TurbineVisual } from './TurbineVisual'
export function TurbineCard({
  turbine,
  onClick,
  detailed = false,
}: {
  turbine: Turbine
  onClick?: () => void
  detailed?: boolean
}) {
  const { t: translateText, tx, dateLabel } = useI18n()
  const fresh = turbine.telemetryState === 'fresh'
  const outdated = turbine.telemetryState === 'stale'

  return (
    <div className={`turbine-card ${turbine.status === 'deviation' ? 'is-warning' : ''}`}>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-xs font-semibold">
          <span
            className={`h-2 w-2 rounded-full ${turbine.id === 'WT-01' ? 'bg-[#8ce4b8]' : 'bg-[#69b7ef]'}`}
          />
          {tx(detailed ? turbine.name : turbine.id)}
        </span>
        <Badge tone={turbine.status === 'deviation' || outdated ? 'amber' : fresh ? 'blue' : 'gray'} dot>
          {tx(
            turbine.status === 'deviation'
              ? 'DEVIATION'
              : fresh
                ? 'FRESH READING'
                : outdated
                  ? 'OUT OF DATE'
                  : turbine.telemetryState === 'unavailable'
                    ? 'UNAVAILABLE'
                    : 'NO READING',
          )}
        </Badge>
      </div>
      <div className="turbine-main">
        <div>
          <span className="text-[10px] text-muted">{translateText('Expected power')}</span>
          <p className="mt-1 text-[30px] font-medium tracking-tight">{tx(percent(turbine.expected))}</p>
          <time className="block text-[10px] text-muted">{timeLabel(turbine.forecastAt)} UTC</time>
          <div className="mt-3 flex items-center gap-1.5 text-[11px] text-muted">
            <Wind size={12} />
            <span className="text-[#bdc9d3]">{tx(turbine.wind.toFixed(1))}</span>
            {translateText(' m/s')}
            {tx(' ')}
            <span className="ml-1 text-[9px] text-muted">{translateText('Forecast')}</span>
          </div>
        </div>
        <TurbineVisual warning={turbine.status === 'deviation'} />
      </div>
      {!detailed && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-[11px]">
          <span className="text-muted">{translateText('Observed power')}</span>
          <span>
            {tx(percent(turbine.observed))}
            {turbine.observedAt && (
              <time className="ml-2 text-[10px] text-muted">{timeLabel(turbine.observedAt)} UTC</time>
            )}
          </span>
        </div>
      )}
      <div className="flex items-center justify-between border-t border-white/5 pt-3 text-[10px] text-muted">
        <span className="flex items-center gap-1">
          <Compass size={11} />
          {tx(turbine.direction)}°
        </span>
        <span className="flex items-center gap-1">
          <Thermometer size={11} />
          {tx(turbine.temperature.toFixed(0))}
          {translateText('°C')}
        </span>
        <span className={turbine.confidence >= 85 ? 'text-[#8cbaaa]' : 'text-amber-300'}>
          {tx(turbine.confidence >= 85 ? 'High' : 'Medium')}
          {translateText(' confidence')}
        </span>
      </div>
      {tx(
        detailed && (
          <div className="mt-5 grid grid-cols-2 gap-4 border-t border-white/5 pt-4">
            <div>
              <p className="text-xs text-muted">{translateText('Observed power')}</p>
              <p className={`mt-1 text-2xl ${turbine.status === 'deviation' ? 'text-amber-300' : ''}`}>
                {tx(percent(turbine.observed))}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted">{translateText('Operating state')}</p>
              <p className="mt-2 text-sm">
                {tx(
                  turbine.status === 'unknown'
                    ? 'Not verified'
                    : turbine.status === 'deviation'
                      ? 'Attention required'
                      : 'Within expected range',
                )}
              </p>
            </div>
          </div>
        ),
      )}
      {detailed && turbine.measurement && (
        <div
          className={`mt-4 rounded-lg border p-3 text-xs leading-6 ${fresh ? 'border-sky-300/20' : 'border-amber-300/20'} text-muted`}
        >
          <p>{translateText(fresh ? 'Current turbine readings' : 'Last received reading')}</p>
          <time>
            {dateLabel(turbine.measurement.timestamp)}{' '}
            {new Date(turbine.measurement.timestamp).getUTCFullYear()} ·{' '}
            {timeLabel(turbine.measurement.timestamp)} UTC
          </time>
          <p>
            {translateText('Observed power')}: {tx(percent(turbine.measurement.power))}
          </p>
          {turbine.measurement.windSpeed !== null && (
            <p>
              {translateText('Measured wind')}: {tx(turbine.measurement.windSpeed.toFixed(1))}{' '}
              {translateText('m/s')}
            </p>
          )}
          {!fresh && (
            <p className="text-amber-300">
              {translateText('This reading is not available as current telemetry.')}
            </p>
          )}
        </div>
      )}
      {detailed && turbine.lastObservation && (
        <div className="mt-4 rounded-lg border border-white/10 p-3 text-xs leading-6 text-muted">
          <p>
            {translateText('Last archived measurement')}: {dateLabel(turbine.lastObservation.timestamp)}{' '}
            {new Date(turbine.lastObservation.timestamp).getUTCFullYear()} ·{' '}
            {timeLabel(turbine.lastObservation.timestamp)} UTC
          </p>
          <p>
            {translateText('Observed power')}:{' '}
            <span className="text-white">{percent(turbine.lastObservation.power)}</span> ·{' '}
            {translateText('Wind')}: {tx(turbine.lastObservation.wind.toFixed(1))} {translateText('m/s')}
          </p>
          <p>{translateText('Historical measurement · not current telemetry')}</p>
        </div>
      )}
      {tx(
        onClick && (
          <button
            onClick={onClick}
            className="mt-3 flex w-full items-center justify-between text-[10px] text-muted hover:text-emerald-300"
          >
            {translateText('View digital twin')}
            <ArrowUpRight size={12} />
          </button>
        ),
      )}
    </div>
  )
}
