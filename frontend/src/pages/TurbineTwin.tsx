import { Bot, GitCompareArrows, Info, TriangleAlert } from 'lucide-react'
import { useI18n } from '../i18n/I18nContext'
import { useOperations } from '../state/OperationsContext'
import { TurbineCard } from '../components/turbine/TurbineCard'
import { Badge, Panel, PanelHeading } from '../components/ui/shared'
import { ForecastChart } from '../components/charts/ForecastChart'
import { TelemetryStatus } from '../components/turbine/TelemetryStatus'
export default function TurbineTwin() {
  const { t, dateLabel } = useI18n()
  const { turbines, forecast, anomalies, telemetry } = useOperations()
  if (!forecast) return null
  return (
    <div className="space-y-5">
      <TelemetryStatus />
      <div className="grid gap-5 md:grid-cols-2">
        {turbines.map((turbine) => (
          <TurbineCard key={turbine.id} turbine={turbine} detailed />
        ))}
      </div>
      <Panel>
        <PanelHeading
          title={t('AI Twin Analysis')}
          icon={<Bot size={17} className="text-emerald-300" />}
          action={<Badge tone="gray">{t('NOT VERIFIED')}</Badge>}
        />
        <div className="flex gap-4 px-5 pb-6">
          <Info size={23} className="shrink-0 text-sky-300" />
          <div>
            <h3 className="text-base font-medium">
              {t(
                telemetry?.available ? 'Operating state needs verification' : 'Current telemetry unavailable',
              )}
            </h3>
            <p className="mt-3 max-w-4xl text-sm leading-7 text-muted">
              {t(
                telemetry?.freshCount
                  ? 'Current readings and future forecasts refer to different times. Receiving measurements alone does not confirm normal operation or an anomaly.'
                  : 'The chart compares expected power under forecast weather conditions. Historical measurements are dated separately. Without current measurements, the system cannot confirm normal operation or detect a current turbine deviation.',
              )}
            </p>
          </div>
        </div>
      </Panel>
      <Panel>
        <PanelHeading
          title={t('Turbine behaviour comparison')}
          subtitle={t('Expected output under forecast weather conditions')}
          icon={<GitCompareArrows size={16} />}
        />
        <div className="p-5">
          <ForecastChart records={forecast.records} height={285} />
        </div>
      </Panel>
      <Panel>
        <PanelHeading
          title={t('Historical deviation screening')}
          subtitle={t(
            'Recorded power difference ≥20 percentage points, similar wind within 0.8 m/s, at least two consecutive hours.',
          )}
        />
        {anomalies.length === 0 ? (
          <p className="px-5 pb-6 text-sm leading-6 text-muted">
            {t(
              'No periods met this rule in the last 90 days of the available measurements. This does not establish current turbine health.',
            )}
          </p>
        ) : (
          <div className="divide-y divide-white/5 px-5">
            {anomalies.map((item) => (
              <div key={item.id} className="flex flex-wrap items-center gap-4 py-5">
                <TriangleAlert size={18} className="text-amber-300" />
                <div>
                  <p className="text-xs text-muted">{dateLabel(item.date)}</p>
                  <p>{item.turbine}</p>
                </div>
                <div className="flex-1">
                  <p className="text-sm">{t(item.title)}</p>
                  <p className="text-xs text-muted">
                    {t('Duration: ')}
                    {item.duration}
                  </p>
                </div>
                <Badge tone="gray">{t('ARCHIVE')}</Badge>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
