import { ArrowRight, Info, LoaderCircle, TriangleAlert } from 'lucide-react'
import { useOperations } from '../../state/OperationsContext'
import { useI18n } from '../../i18n/I18nContext'
import { Button } from '../ui/button'
import { telemetryLabel } from '../../types/telemetry'
export function OperatorBrief() {
  const { forecast, busy, error, setPage, telemetry } = useOperations()
  const { t } = useI18n()
  const stale = forecast?.stale || !!error
  const Icon = busy ? LoaderCircle : stale ? TriangleAlert : Info
  return (
    <section
      className={`operator-brief ${stale ? 'warning' : 'info'}`}
      aria-label={t('OPERATOR BRIEFING')}
      data-testid="operator-brief"
    >
      <div className="brief-icon">
        <Icon size={22} className={busy ? 'animate-spin' : ''} />
      </div>
      <div className="brief-copy" aria-live="polite">
        <span>{t('OPERATOR BRIEFING')}</span>
        <h2>
          {t(
            busy
              ? 'Forecast update in progress'
              : stale
                ? 'Forecast update needs attention'
                : telemetry?.available
                  ? 'Forecast and turbine readings available'
                  : telemetryLabel(telemetry),
          )}
        </h2>
        <p>
          {t(
            busy
              ? 'The backend is receiving weather and running the trained model. Follow the execution log.'
              : stale
                ? 'The last published forecast is shown. Check its date before using it for operational decisions.'
                : telemetry?.available
                  ? 'Measured power is shown with its timestamp. The forecast covers future hours; turbine operating state still requires verification.'
                  : 'The power forecast is ready. Connect a source of current turbine measurements to see actual output.',
          )}
        </p>
      </div>
      <Button
        variant="outline"
        onClick={() => setPage(stale || busy ? 'agent' : telemetry?.available ? 'twin' : 'diagnostics')}
      >
        {t(
          stale || busy
            ? 'View update progress'
            : telemetry?.available
              ? 'View digital twin'
              : 'View connection details',
        )}
        <ArrowRight size={14} />
      </Button>
    </section>
  )
}
