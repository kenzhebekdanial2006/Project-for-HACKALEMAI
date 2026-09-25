import { useI18n } from '../../i18n/I18nContext'
import { Bot, Check, Clock3 } from 'lucide-react'
import { useOperations } from '../../state/OperationsContext'
import { timeLabel } from '../../lib/utils'

export function OperationsStatus() {
  const { t: translateText, tx } = useI18n()

  const { agent, events, nextCheck, busy, setPage } = useOperations()
  return (
    <div className="operations-status">
      <button onClick={() => setPage('agent')}>
        <Bot size={13} />
        <span>
          {translateText('Agent ')}
          <b>{tx(agent.state)}</b>
        </span>
        <i className={`status-dot ${busy ? 'pulse-dot' : ''}`} />
      </button>
      <span className="operations-last">
        <Check size={12} />
        {tx(busy ? agent.task : `Last action: ${events.at(-1)?.title || 'Waiting for data'}`)}
      </span>
      {tx(
        nextCheck && (
          <span className="operations-next">
            <Clock3 size={12} />
            {translateText('Next forecast ')}
            <b>
              {tx(timeLabel(nextCheck))}
              {translateText(' UTC')}
            </b>
          </span>
        ),
      )}
    </div>
  )
}
