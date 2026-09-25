import { CalendarDays } from 'lucide-react'
import { useI18n } from '../../i18n/I18nContext'
import { useOperations } from '../../state/OperationsContext'
export function PageHeading({ title, description }: { title: string; description: string }) {
  const { t, dateLabel } = useI18n()
  const { connected, page, serverTime } = useOperations()
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">
          <span className={`status-dot ${connected ? 'text-emerald-300' : 'text-amber-300'}`} />
          {t(page === 'replay' ? 'HISTORICAL OPERATIONS' : 'LIVE OPERATIONS')}
          <span className="eyebrow-separator">/</span>
          <span className="text-[#6b7a85]">{t(connected ? 'API CONNECTED' : 'API DISCONNECTED')}</span>
        </div>
        <h1>
          {title}
          <span className="heading-dot">.</span>
        </h1>
        <p>{description}</p>
      </div>
      {serverTime && (
        <div className="page-heading-tools">
          <div className="date-chip">
            <CalendarDays size={13} />
            {dateLabel(serverTime)} {new Date(serverTime).getUTCFullYear()}
            <span>UTC</span>
          </div>
        </div>
      )}
    </div>
  )
}
