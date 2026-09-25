import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  Clock3,
  Info,
  Maximize2,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  TriangleAlert,
  Zap,
} from 'lucide-react'
import { useState } from 'react'
import { useI18n } from '../i18n/I18nContext'
import { useOperations } from '../state/OperationsContext'
import { Badge, Panel, PanelHeading, TextLink } from '../components/ui/shared'
import { ForecastConfidence } from '../components/confidence/ForecastConfidence'
import { ForecastChart } from '../components/charts/ForecastChart'
import { TurbineCard } from '../components/turbine/TurbineCard'
import { TurbineVisual } from '../components/turbine/TurbineVisual'
import { AgentTimeline } from '../components/agent/AgentTimeline'
import { ForecastExplanation } from '../components/forecast/ForecastExplanation'
import { OperationsStatus } from '../components/agent/OperationsStatus'
import { OperatorBrief } from '../components/agent/OperatorBrief'
import { percent, timeLabel } from '../lib/utils'
import type { ForecastRecord } from '../types/forecast'
import { telemetryLabel } from '../types/telemetry'

export default function Overview() {
  const { t, tx, dateLabel, number } = useI18n()
  const { forecast, turbines, agent, events, busy, anomalies, setPage, telemetry } = useOperations()
  const [selected, setSelected] = useState<ForecastRecord | null>(null)
  const [hours, setHours] = useState(48)
  if (!forecast?.records.length) return null
  const average =
    forecast.records
      .slice(0, 6)
      .reduce((sum, row) => sum + (row.WT01.prediction + row.WT02.prediction) / 2, 0) / 6
  const peak = forecast.records.reduce((a, b) =>
    a.WT01.prediction + a.WT02.prediction > b.WT01.prediction + b.WT02.prediction ? a : b,
  )
  const peakPower = (peak.WT01.prediction + peak.WT02.prediction) / 2
  const low = forecast.records.reduce((a, b) => (a.windSpeed120m < b.windSpeed120m ? a : b))
  const attention =
    anomalies.filter((item) => item.active).length +
    (forecast.telemetryAvailable ? 0 : 1) +
    (forecast.stale || forecast.sourceState !== 'Primary' ? 1 : 0)
  const first = forecast.records[0]
  return (
    <div className="space-y-5">
      <OperatorBrief />
      <OperationsStatus />
      <div className="kpi-grid">
        <Panel className="kpi-card">
          <div className="kpi-label">
            <span>{t('Expected power')}</span>
            <Zap size={15} />
          </div>
          <div className="kpi-number-row">
            <strong className="metric-value">{percent(average)}</strong>
          </div>
          <p className="kpi-caption">
            {t('Next 6 hours')}
            <span>{t('Mean of two turbines · % rated')}</span>
          </p>
        </Panel>
        <Panel className="kpi-card">
          <div className="kpi-label">
            <span>{t('Peak generation')}</span>
            <TrendingUp size={15} />
          </div>
          <div className="kpi-number-row">
            <strong className="metric-value">{percent(peakPower)}</strong>
          </div>
          <p className="kpi-caption">
            {dateLabel(peak.timestamp)} · {timeLabel(peak.timestamp)} UTC
            <span>{t('Mean of two turbines · % rated')}</span>
          </p>
        </Panel>
        <Panel className="kpi-card">
          <div className="kpi-label mb-3">
            <span>{t('Forecast confidence')}</span>
            <ShieldCheck size={15} />
          </div>
          <ForecastConfidence score={forecast.confidence} factors={forecast.factors} />
          <p className="mt-2 text-[10px] text-muted">{t('System confidence indicator')}</p>
        </Panel>
        <Panel className="kpi-card">
          <div className="kpi-label">
            <span>{t('Attention items')}</span>
            <TriangleAlert size={15} />
          </div>
          <div className="kpi-number-row">
            <strong className={`metric-value ${attention ? 'text-amber-300' : 'text-emerald-300'}`}>
              {attention}
            </strong>
            <Badge tone={attention ? 'amber' : 'green'}>{t(attention ? 'REVIEW' : 'NO ACTIVE ALERTS')}</Badge>
          </div>
          <p className="kpi-caption">{t(telemetryLabel(telemetry))}</p>
        </Panel>
      </div>
      <p className="power-unit-note">
        {t('Power is shown as a percentage of rated output, not energy in MWh.')}
      </p>
      <div className="overview-main">
        <Panel className="forecast-panel">
          <PanelHeading
            title={t('Forecast overview')}
            subtitle={t(`Expected output across the next ${hours} hours`)}
            icon={<Activity size={15} className="text-emerald-200" />}
            action={
              <div className="flex items-center gap-3">
                <div className="segmented">
                  {[24, 48].map((value) => (
                    <button
                      key={value}
                      className={hours === value ? 'selected' : ''}
                      onClick={() => setHours(value)}
                    >
                      {value}
                      {t('h')}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => setPage('forecast')}
                  className="text-muted hover:text-white"
                  aria-label={t('Expand forecast')}
                >
                  <Maximize2 size={14} />
                </button>
              </div>
            }
          />
          <div className="forecast-insight">
            <span className="flex items-center gap-2">
              <span className="status-dot text-sky-300" />
              {forecast.source} · {forecast.modelVersion}
            </span>
            <span>
              {number(first.windSpeed120m)} {t('m/s')} · {t('Forecast wind')}
            </span>
          </div>
          <div className="px-5 pb-2 pt-6">
            <ForecastChart records={forecast.records.slice(0, hours)} onSelect={setSelected} height={228} />
          </div>
          <div className="forecast-footer">
            <span>
              <Clock3 size={12} />
              {t('Next update at ')}
              {timeLabel(forecast.nextUpdate)} UTC
            </span>
            <TextLink onClick={() => setPage('forecast')}>{t('Explore forecast')}</TextLink>
          </div>
        </Panel>
        <Panel className="fleet-panel">
          <PanelHeading
            title={t('Wind farm status')}
            action={
              <Badge tone={telemetry?.available ? 'blue' : 'gray'}>
                {t(telemetry?.available ? 'RECEIVING DATA' : 'CHECK SOURCE')}
              </Badge>
            }
          />
          <div className="farm-visual-wrap">
            <div className="farm-coordinates">
              WT-01 / WT-02<span>{t('Forecast comparison')}</span>
            </div>
            <TurbineVisual landscape />
          </div>
          <div className="fleet-turbines">
            {turbines.map((turbine) => (
              <TurbineCard key={turbine.id} turbine={turbine} onClick={() => setPage('twin')} />
            ))}
          </div>
        </Panel>
      </div>
      <div className="overview-bottom">
        <Panel>
          <PanelHeading
            title={t('AI Agent activity')}
            icon={<Bot size={16} className="text-emerald-200" />}
            subtitle={t('Actual backend execution events')}
            action={
              <Badge dot tone={busy ? 'blue' : 'green'}>
                {t(agent.state.toUpperCase())}
              </Badge>
            }
          />
          <div className="px-5 pb-2">
            <AgentTimeline events={events} compact busy={busy} />
          </div>
          <div className="card-footer">
            <span className="flex items-center gap-2 text-[10px] text-muted">
              <span className="status-dot text-emerald-300" />
              {t(agent.task)}
            </span>
            <TextLink onClick={() => setPage('agent')}>{t('Agent control center')}</TextLink>
          </div>
        </Panel>
        <Panel className="summary-panel">
          <PanelHeading
            title={t('Forecast summary')}
            icon={<Sparkles size={15} className="text-emerald-200" />}
            action={<Badge tone="blue">{t('MODEL OUTPUT')}</Badge>}
          />
          <div className="summary-content">
            <div className="summary-lead">
              <div className="summary-icon">
                <Activity size={18} />
              </div>
              <div>
                <h3>{t('48-hour operating outlook')}</h3>
                <p>{t('Calculated from the latest available ECMWF run and the trained weather model.')}</p>
              </div>
            </div>
            <div className="summary-fact">
              <ArrowUpRight size={15} className="text-emerald-300" />
              <p>
                {t('Peak generation')}: <b>{percent(peakPower)}</b> · {dateLabel(peak.timestamp)}{' '}
                {timeLabel(peak.timestamp)} UTC.
              </p>
            </div>
            <div className="summary-fact">
              <ArrowDownRight size={15} className="text-sky-300" />
              <p>
                {t('Lowest forecast wind')}:{' '}
                <b>
                  {number(low.windSpeed120m)} {t('m/s')}
                </b>{' '}
                · {dateLabel(low.timestamp)} {timeLabel(low.timestamp)} UTC.
              </p>
            </div>
            <div className="summary-fact">
              <Info size={15} className="text-amber-300" />
              <p>
                {t(
                  'Expected ranges use the model validation errors. They are not a guarantee of future coverage.',
                )}
              </p>
            </div>
          </div>
          <div className="card-footer">
            <span className="text-[10px] text-muted">
              {t('Weather run')}: {dateLabel(forecast.weatherRun)} {timeLabel(forecast.weatherRun)} UTC
            </span>
            <TextLink onClick={() => setPage('diagnostics')}>{t('Validation metrics')}</TextLink>
          </div>
        </Panel>
      </div>
      <div className="overview-footnote">
        <span>
          <ShieldCheck size={12} />
          {t('Agentic intelligence for wind energy operations')}
        </span>
        <span>{tx('Predict. Understand. Act.')}</span>
      </div>
      <ForecastExplanation record={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
