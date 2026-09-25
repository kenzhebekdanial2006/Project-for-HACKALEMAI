import {
  ArrowRight,
  Bot,
  Check,
  CloudDownload,
  Database,
  GitCompareArrows,
  LoaderCircle,
  Radio,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Workflow,
} from 'lucide-react'
import { useI18n } from '../i18n/I18nContext'
import { useOperations } from '../state/OperationsContext'
import { Badge, Panel, PanelHeading } from '../components/ui/shared'
import { Button } from '../components/ui/button'
import { AgentTimeline } from '../components/agent/AgentTimeline'
import { timeLabel } from '../lib/utils'
import type { AgentStage } from '../types/agent'
const stages: { label: AgentStage; icon: typeof Bot; description: string }[] = [
  { label: 'Weather', icon: CloudDownload, description: 'Receive weather feed' },
  { label: 'Validation', icon: ShieldCheck, description: 'Check data quality' },
  { label: 'Feature Preparation', icon: Database, description: 'Prepare model inputs' },
  { label: 'Forecast', icon: Sparkles, description: 'Predict both turbines' },
  { label: 'Twin Analysis', icon: GitCompareArrows, description: 'Check measurement availability' },
  { label: 'Decision', icon: Workflow, description: 'Evaluate next action' },
  { label: 'Publish', icon: Send, description: 'Deliver the forecast' },
]
export default function Agent() {
  const { t } = useI18n()
  const { agent, busy, refresh, events, forecast, connected, nextCheck } = useOperations()
  const runStart = events.map((event) => event.title).lastIndexOf('Requesting weather run')
  const currentEvents = events.slice(Math.max(0, runStart))
  return (
    <div className="space-y-5">
      <Panel className="agent-status-panel">
        <div className="agent-orb">
          <Bot size={34} strokeWidth={1.3} />
          <span />
        </div>
        <div className="flex-1">
          <div className="mb-2 flex items-center gap-3">
            <p className="text-[10px] tracking-[.15em] text-muted">{t('CURRENT TASK')}</p>
            <Badge dot tone={connected ? 'green' : 'amber'}>
              {t(agent.state.toUpperCase())}
            </Badge>
          </div>
          <h2 className="text-xl font-medium">{t(agent.task)}</h2>
          <p className="mt-2 text-xs text-muted">
            {t('Weather source')}: {t(agent.source)} · {forecast?.modelVersion || '—'}
          </p>
        </div>
        <div className="agent-status-stat">
          <p>
            48<span>{t(' hours')}</span>
          </p>
          <small>{t('Continuous forecast horizon')}</small>
        </div>
      </Panel>
      <Panel>
        <PanelHeading
          title={t('Agent workflow')}
          subtitle={t('Actual backend execution events')}
          icon={<Workflow size={16} className="text-emerald-300" />}
          action={
            <Badge dot tone={busy ? 'blue' : 'gray'}>
              {t(busy ? 'PIPELINE RUNNING' : 'MONITORING')}
            </Badge>
          }
        />
        <div className="workflow">
          {stages.map((stage, index) => {
            const running = busy && agent.stage === stage.label
            const warning = currentEvents.some(
              (event) => event.stage === stage.label && event.status === 'warning',
            )
            const completed = currentEvents.some(
              (event) => event.stage === stage.label && event.status === 'completed',
            )
            const label = running ? 'Running' : warning ? 'Warning' : completed ? 'Completed' : 'Waiting'
            return (
              <div
                className={`workflow-stage ${running ? 'running' : ''} ${warning ? 'warning' : ''}`}
                key={stage.label}
              >
                <div className="workflow-icon">
                  <stage.icon size={21} strokeWidth={1.5} />
                </div>
                <span className="workflow-index">0{index + 1}</span>
                <h3>{t(stage.label)}</h3>
                <p>{t(stage.description)}</p>
                <div className="workflow-state">
                  {running ? (
                    <LoaderCircle size={11} className="animate-spin" />
                  ) : completed ? (
                    <Check size={11} />
                  ) : (
                    <span className="status-dot" />
                  )}
                  {t(label)}
                </div>
                {index < stages.length - 1 && <ArrowRight className="workflow-arrow" size={14} />}
              </div>
            )
          })}
        </div>
      </Panel>
      <div className="grid gap-5 xl:grid-cols-[1fr_330px]">
        <Panel>
          <PanelHeading
            title={t('Agent event stream')}
            subtitle={t('Every action recorded with a clear operational explanation')}
            icon={<Radio size={16} />}
            action={
              <Badge tone={connected ? 'blue' : 'amber'} dot>
                {t(connected ? 'API CONNECTED' : 'API DISCONNECTED')}
              </Badge>
            }
          />
          <div className="min-h-72 px-5 pb-5" role="log" aria-label={t('Agent events')} aria-live="polite">
            {events.length ? (
              <AgentTimeline events={events} busy={busy} />
            ) : (
              <p className="text-sm text-muted">{t('Waiting for backend events')}</p>
            )}
          </div>
        </Panel>
        <div className="space-y-5">
          <Panel className="p-5">
            <h3 className="text-base font-medium">{t('Forecast execution')}</h3>
            <p className="mb-5 mt-2 text-xs leading-6 text-muted">
              {t(
                'Request current weather and recalculate both turbines using the trained model. Updates also run automatically on the server.',
              )}
            </p>
            <Button className="w-full" variant="outline" disabled={busy} onClick={() => void refresh()}>
              <RefreshCw size={14} className={busy ? 'animate-spin' : ''} />
              {t(busy ? 'Updating…' : 'Refresh Forecast')}
            </Button>
            <p className="mt-4 text-xs text-muted">
              {t('Next check')}: {nextCheck ? timeLabel(nextCheck) : '—'} UTC
            </p>
          </Panel>
          <Panel className="p-5">
            <h3 className="text-xs font-medium">{t('Recovery policy')}</h3>
            <div className="mt-4 space-y-4 text-xs leading-6 text-muted">
              {[
                'Request the latest eligible ECMWF run',
                'Try the previous run if unavailable',
                'Use a validated local cache only while it is recent',
                'Keep the last forecast with a stale-data warning if recovery fails',
              ].map((item, index) => (
                <p key={item}>
                  <span className="mr-2 text-emerald-300">0{index + 1}</span>
                  {t(item)}
                </p>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}
