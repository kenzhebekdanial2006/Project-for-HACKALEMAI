import { Database, Gauge, Info, Layers3, Server, ShieldCheck } from 'lucide-react'
import { useI18n } from '../i18n/I18nContext'
import { useOperations } from '../state/OperationsContext'
import { Badge, LoadingState, Panel, PanelHeading } from '../components/ui/shared'
import { ForecastConfidence } from '../components/confidence/ForecastConfidence'
import { TelemetryStatus } from '../components/turbine/TelemetryStatus'
import { telemetryLabel } from '../types/telemetry'
export default function Diagnostics() {
  const { t, number, dateLabel } = useI18n()
  const { diagnostics: data, forecast, agent, connected, telemetry } = useOperations()
  if (!data) return <LoadingState label="Loading model and datasets" />
  const sections = [
    {
      title: 'Data sources',
      icon: Server,
      rows: [
        ['Operations API', connected ? 'Connected' : 'Unavailable'],
        ['Weather API', agent.source],
        ['Historical Weather Archive', `${data.archiveRuns}`],
        ['Current turbine readings', telemetryLabel(telemetry)],
        ['External language model', data.llmConfigured ? `${data.llmProvider} · ${data.llmModel}` : 'Not configured'],
      ],
    },
    {
      title: 'Model',
      icon: Layers3,
      rows: [
        ['Model version', data.modelVersion],
        ['Model type', data.modelType],
        ['Forecast horizon', '48 hours'],
        ['Input features', String(data.features)],
        ['Training rows', number(data.trainingRows, 0)],
      ],
    },
    {
      title: 'Dataset',
      icon: Database,
      rows: [
        ...data.datasets.map((item) => [item.id, number(item.records, 0)]),
        ['Resolution', '10 minutes'],
        ['Training start', dateLabel(data.trainingStart)],
        ['Training cutoff', dateLabel(data.trainingEnd) + ' ' + new Date(data.trainingEnd).getUTCFullYear()],
      ],
    },
  ]
  return (
    <div className="space-y-5">
      <TelemetryStatus setup />
      <div className="info-banner">
        <Info size={17} />
        <p>
          {t(
            'Metrics below are read from the trained model metadata. Weather-model validation errors are used; sensor-based training scores are not substituted.',
          )}
        </p>
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        {sections.map((section) => (
          <Panel key={section.title}>
            <PanelHeading
              title={t(section.title)}
              icon={<section.icon size={16} className="text-sky-300" />}
            />
            <div className="space-y-5 px-5 pb-6">
              {section.rows.map(([label, value]) => (
                <div key={label} className="flex items-start justify-between gap-4 text-xs">
                  <span className="text-muted">{t(label)}</span>
                  <span className="text-right">{t(value)}</span>
                </div>
              ))}
            </div>
          </Panel>
        ))}
      </div>
      <Panel>
        <PanelHeading
          title={t('Validation metrics')}
          subtitle={t('Purged time split · validation from ') + data.validationStart}
          icon={<Gauge size={16} className="text-sky-300" />}
          action={<Badge tone="blue">{t('FROM MODEL FILE')}</Badge>}
        />
        <div className="grid gap-5 px-5 pb-6 md:grid-cols-3">
          {[
            {
              name: 'Mean absolute error',
              value: number(data.metrics.MAE * 100, 2),
              unit: 'pp',
              detail: 'MAE · normalized power percentage points',
            },
            {
              name: 'Root mean squared error',
              value: number(data.metrics.RMSE * 100, 2),
              unit: 'pp',
              detail: 'RMSE · normalized power percentage points',
            },
            {
              name: 'Coefficient of determination',
              value: number(data.metrics.R2, 3),
              unit: '',
              detail: 'R² · validation set',
            },
          ].map((metric) => (
            <div key={metric.name} className="rounded-xl border border-white/5 bg-white/[.015] p-5">
              <p className="text-xs text-muted">{t(metric.name)}</p>
              <p className="my-4 text-4xl font-medium">
                {metric.value}
                <span className="ml-2 text-base text-muted">{t(metric.unit)}</span>
              </p>
              <p className="text-[10px] text-muted">{t(metric.detail)}</p>
            </div>
          ))}
        </div>
        <div className="table-scroll px-5 pb-6">
          <table className="w-full">
            <thead>
              <tr>
                <th>{t('Turbine')}</th>
                <th>MAE ({t('pp')})</th>
                <th>RMSE ({t('pp')})</th>
                <th>R²</th>
                <th>
                  {t('Range half-width')} ({t('pp')})
                </th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.turbineMetrics).map(([key, metrics]) => (
                <tr key={key}>
                  <td>{key === 'WT_1' ? 'WT-01' : 'WT-02'}</td>
                  <td>{number(metrics.MAE * 100, 2)}</td>
                  <td>{number(metrics.RMSE * 100, 2)}</td>
                  <td>{number(metrics.R2, 3)}</td>
                  <td>{number(data.intervalErrors[key] * 100, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel>
          <PanelHeading
            title={t('Forecast confidence')}
            subtitle={t('Operator-facing system health indicator')}
            icon={<ShieldCheck size={16} />}
          />
          <div className="px-5 pb-6">
            {forecast && <ForecastConfidence score={forecast.confidence} factors={forecast.factors} />}
            <p className="mt-5 text-xs leading-6 text-muted">
              {t(
                'The score averages weather completeness, validation-based model quality and freshness. Unavailable turbine behaviour verification and independent weather agreement each subtract 10 points. Receiving measurements alone does not verify behaviour. This is not a probability of forecast accuracy.',
              )}
            </p>
          </div>
        </Panel>
        <Panel>
          <PanelHeading
            title={t('Data provenance')}
            subtitle={t('Loaded artifacts and operational limits')}
          />
          <div className="space-y-4 px-5 pb-6 text-xs leading-6 text-muted">
            <p>
              {t('Model')}: <span className="text-white">catboost_weather.cbm</span>
            </p>
            <p className="break-all">SHA-256: {data.modelFingerprint}</p>
            <p>
              {t(
                'Weather availability is estimated as run initialization plus 6 hours 10 minutes. It is not a verified publication timestamp.',
              )}
            </p>
            <p>
              {t(
                'Expected ranges use the model validation errors. They are not a guarantee of future coverage.',
              )}
            </p>
          </div>
        </Panel>
      </div>
    </div>
  )
}
