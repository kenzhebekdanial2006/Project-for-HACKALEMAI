import { useI18n } from '../../i18n/I18nContext'
import { Check, ChevronRight, LoaderCircle, TriangleAlert } from 'lucide-react'
import { motion } from 'framer-motion'
import type { AgentEvent } from '../../types/agent'
export function AgentTimeline({
  events,
  compact = false,
  busy = false,
}: {
  events: AgentEvent[]
  compact?: boolean
  busy?: boolean
}) {
  const { tx } = useI18n()

  return (
    <div className={`agent-timeline ${compact ? 'compact' : ''}`}>
      {tx(
        events.slice(compact ? -5 : -30).map((event, i, shown) => (
          <motion.div
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            key={event.id}
            className="timeline-event"
          >
            <span className="timeline-time">{tx(compact ? event.time.slice(0, 5) : event.time)}</span>
            <span className={`timeline-marker ${event.status === 'warning' ? 'warning' : ''}`}>
              {tx(
                busy && i === shown.length - 1 ? (
                  <LoaderCircle size={11} className="animate-spin" />
                ) : event.status === 'warning' ? (
                  <TriangleAlert size={10} />
                ) : (
                  <Check size={10} />
                ),
              )}
            </span>
            <div className="min-w-0">
              <p className="timeline-title">{tx(event.title)}</p>
              <p className="timeline-detail">{tx(event.detail)}</p>
            </div>
            {tx(compact && <ChevronRight size={12} className="ml-auto shrink-0 text-[#46565f]" />)}
          </motion.div>
        )),
      )}
    </div>
  )
}
