import { useI18n } from '../../i18n/I18nContext'
import {
  Activity,
  ArrowUpRight,
  AudioLines,
  Bot,
  ChartNoAxesCombined,
  ChevronRight,
  CircleHelp,
  Clock3,
  LayoutDashboard,
  Radio,
  Wind,
  X,
} from 'lucide-react'
import { useOperations } from '../../state/OperationsContext'
import type { Page } from '../../types/forecast'
import { Dialog } from '../ui/dialog'
import { useState } from 'react'
import { OperatorGuide } from '../forecast/OperatorGuide'
export const navigation = [
  { page: 'overview', label: 'Overview', icon: LayoutDashboard },
  { page: 'forecast', label: '48h Forecast', icon: ChartNoAxesCombined },
  { page: 'twin', label: 'Turbine Twin', icon: Wind },
  { page: 'agent', label: 'AI Agent', icon: Bot },
  { page: 'replay', label: 'Historical Replay', icon: Clock3 },
  { page: 'diagnostics', label: 'Diagnostics', icon: Activity },
] satisfies { page: Page; label: string; icon: typeof Wind }[]
export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t: translateText, tx } = useI18n()

  const { page, setPage, connected, agent, diagnostics } = useOperations()
  const [help, setHelp] = useState(false)
  return (
    <>
      {tx(
        open && (
          <button
            className="sidebar-backdrop"
            onClick={onClose}
            aria-label={translateText('Close navigation')}
          />
        ),
      )}
      <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
        <a className="brand" href="#overview" onClick={onClose}>
          <div className="brand-mark">
            <AudioLines size={25} strokeWidth={1.6} />
          </div>
          <div>
            <div className="brand-name">
              {translateText('WindOps')}
              <span>{translateText(' AI')}</span>
            </div>
            <p>{translateText('Wind Farm Digital Twin')}</p>
          </div>
        </a>
        <button className="mobile-nav-close" aria-label={translateText('Close navigation')} onClick={onClose}>
          <X size={20} />
        </button>
        <div className="workspace-label">
          {translateText('WORKSPACE')}
          <span>01</span>
        </div>
        <div className="site-switcher">
          <div className="site-icon">
            <Wind size={18} />
          </div>
          <div>
            <strong>{translateText('Wind farm')} · WT-01 / WT-02</strong>
            <p>{translateText('Kazakhstan')} · UTC+5</p>
          </div>
          <span className="status-dot text-emerald-300" />
        </div>
        <p className="nav-caption">{translateText('OPERATIONS')}</p>
        <nav>
          {tx(
            navigation.map(({ page: p, label, icon: Icon }) => (
              <a
                key={p}
                href={`#${p}`}
                data-page={p}
                onClick={() => {
                  setPage(p)
                  onClose()
                }}
                aria-current={page === p ? 'page' : undefined}
                className={`nav-item ${page === p ? 'active' : ''}`}
              >
                <Icon size={17} strokeWidth={1.6} />
                <span>{tx(label)}</span>
                {tx(
                  p === 'agent' ? (
                    <span className="nav-live">{translateText(agent.active ? 'LIVE' : 'WAITING')}</span>
                  ) : page === p ? (
                    <ChevronRight size={13} className="ml-auto" />
                  ) : null,
                )}
              </a>
            )),
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="system-card">
            <div className="mb-4 flex items-center gap-2 text-[10px] font-medium tracking-[.12em] text-[#8a9b9c]">
              <Radio size={12} />
              {translateText('SYSTEM HEALTH')}
            </div>
            <div>
              <span>{translateText('System')}</span>
              <span className={connected ? 'text-emerald-300' : 'text-amber-300'}>
                <i className="status-dot" />
                {translateText(connected ? 'Online' : 'Unavailable')}
              </span>
            </div>
            <div>
              <span>{translateText('Weather API')}</span>
              <span className={agent.source === 'Primary' ? 'text-emerald-300' : 'text-amber-300'}>
                {tx(agent.source)}
              </span>
            </div>
            <div>
              <span>{translateText('Model version')}</span>
              <span className="font-mono text-[#b2bdc6]">{diagnostics?.modelVersion || '—'}</span>
            </div>
          </div>
          <button className="help-link" onClick={() => setHelp(true)}>
            <CircleHelp size={16} />
            {translateText('Operator guide')}
            <ArrowUpRight size={13} className="ml-auto" />
          </button>
          <div className="sidebar-footer">
            <div className="avatar">{translateText('OP')}</div>
            <div>
              <strong>{translateText('Operator workspace')}</strong>
              <p>{translateText('Connected data services')}</p>
            </div>
            <span className="status-dot text-emerald-300" />
          </div>
        </div>
      </aside>
      <Dialog
        open={help}
        onOpenChange={setHelp}
        title={translateText('Your operator workspace')}
        description={translateText('Predict. Understand. Act.')}
      >
        <OperatorGuide />
      </Dialog>
    </>
  )
}
