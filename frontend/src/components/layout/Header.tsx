import { useI18n } from '../../i18n/I18nContext'
import { Bell, ChevronRight, Menu, RefreshCw, Settings2, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { useOperations } from '../../state/OperationsContext'
import { Button } from '../ui/button'
import { Dialog } from '../ui/dialog'
import { Badge } from '../ui/shared'
import { navigation } from './Sidebar'
import { LanguageSelector } from './LanguageSelector'
export function Header({ onMenu }: { onMenu: () => void }) {
  const { t: translateText, tx } = useI18n()

  const { page, agent, connected, diagnostics, notifications, markRead, busy, refresh, lastUpdate } =
    useOperations()
  const [showNotifications, setShowNotifications] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [reduceMotion, setReduceMotion] = useState(localStorage.getItem('windops-reduced-motion') === 'true')
  const unread = notifications.filter((n) => !n.read).length
  return (
    <>
      <header className="header">
        <div className="header-location">
          <Button
            variant="ghost"
            size="icon"
            className="menu-toggle"
            onClick={onMenu}
            aria-label={translateText('Open navigation')}
          >
            <Menu size={19} />
          </Button>
          <span className="hidden text-[#71808c] xl:inline">{translateText('Workspace')}</span>
          <ChevronRight size={12} className="hidden text-[#4a5964] xl:block" />
          <span>{tx(navigation.find((n) => n.page === page)?.label)}</span>
        </div>
        <div className="header-feeds">
          <span>
            <i className={`status-dot ${connected ? 'text-emerald-300' : 'text-amber-300'}`} />
            {translateText(connected ? 'System online' : 'API DISCONNECTED')}
          </span>
          <span>
            <i
              className={`status-dot ${agent.source === 'Primary' ? 'text-emerald-300' : 'text-amber-300'}`}
            />
            {translateText('Weather ')}
            {tx(agent.source)}
          </span>
          <span className="header-agent">
            <i className="status-dot pulse-dot text-emerald-300" />
            {translateText('AI Agent ')}
            {tx(agent.active ? 'active' : 'waiting')}
          </span>
        </div>
        <div className="header-actions">
          <LanguageSelector />
          <div className="header-updated">
            {translateText('Last update ')}
            <b>{tx(lastUpdate)}</b>
            <span>{translateText('48h forecast')}</span>
          </div>
          <Button
            className="refresh-button"
            aria-label={translateText(busy ? 'Updating…' : 'Refresh Forecast')}
            variant="outline"
            size="sm"
            onClick={() => void refresh()}
            disabled={busy}
          >
            <RefreshCw size={13} className={busy ? 'animate-spin' : ''} />
            <span className="refresh-label">{tx(busy ? 'Updating…' : 'Refresh Forecast')}</span>
          </Button>
          <button
            className="icon-button notification-button"
            aria-label={translateText(`Notifications, ${unread} unread`)}
            onClick={() => setShowNotifications(true)}
          >
            <Bell size={17} />
            {tx(unread > 0 && <i />)}
          </button>
          <button
            className="icon-button settings-button"
            aria-label={translateText('Settings')}
            onClick={() => setShowSettings(true)}
          >
            <Settings2 size={17} />
          </button>
        </div>
      </header>
      <Dialog
        open={showNotifications}
        onOpenChange={setShowNotifications}
        title={translateText('Notification center')}
        description={translateText(`${unread} unread operational updates`)}
        drawer
      >
        <Button variant="outline" size="sm" className="mb-5" onClick={markRead} disabled={unread === 0}>
          {translateText('Mark all as read')}
        </Button>
        <div className="space-y-3">
          {tx(
            notifications.map((n) => (
              <div
                className={`rounded-xl border p-4 ${n.read ? 'border-white/5 opacity-65' : 'border-white/10 bg-white/[.025]'}`}
                key={n.id}
              >
                <div className="mb-3 flex items-center justify-between">
                  <Badge
                    tone={n.severity === 'Critical' ? 'red' : n.severity === 'Warning' ? 'amber' : 'blue'}
                  >
                    {tx(n.severity)}
                  </Badge>
                  <time className="text-[10px] text-muted">
                    {tx(n.time)}
                    {translateText(' UTC')}
                  </time>
                </div>
                <h3 className="text-sm font-medium">{tx(n.title)}</h3>
                <p className="mt-2 text-xs leading-relaxed text-muted">{tx(n.description)}</p>
              </div>
            )),
          )}
        </div>
      </Dialog>
      <Dialog
        open={showSettings}
        onOpenChange={setShowSettings}
        title={translateText('Workspace settings')}
        description={translateText('Display preferences for this device.')}
      >
        <LanguageSelector expanded />
        <p className="mb-6 mt-2 text-xs leading-5 text-muted">
          {translateText('Saved on this device. Forecast values do not change when you switch languages.')}
        </p>
        <div className="flex items-center justify-between rounded-lg border border-white/10 p-4">
          <div>
            <p className="text-sm">{translateText('Reduce motion')}</p>
            <p className="mt-1 text-xs text-muted">{translateText('Pause turbine and status animations.')}</p>
          </div>
          <input
            aria-label={translateText('Reduce motion')}
            type="checkbox"
            className="h-4 w-4 accent-emerald-300"
            checked={reduceMotion}
            onChange={(e) => {
              setReduceMotion(e.target.checked)
              localStorage.setItem('windops-reduced-motion', String(e.target.checked))
              document.documentElement.classList.toggle('reduce-motion', e.target.checked)
            }}
          />
        </div>
        <div className="mt-5 flex items-center gap-2 text-xs text-muted">
          <SlidersHorizontal size={15} />
          {translateText('Display timezone: UTC · Normalized power: %')}
        </div>
        <p className="mt-4 text-xs leading-relaxed text-muted">
          {translateText('Model')}: {diagnostics?.modelVersion || '—'} ·{' '}
          {translateText(connected ? 'API CONNECTED' : 'API DISCONNECTED')}
        </p>
      </Dialog>
    </>
  )
}
