import { ChartNoAxesCombined, GitCompareArrows, ShieldCheck } from 'lucide-react'
import { useI18n } from '../../i18n/I18nContext'

export function OperatorGuide() {
  const { t } = useI18n()
  const items = [
    {
      icon: GitCompareArrows,
      title: 'Expected vs. observed',
      text: 'Expected power is a forecast for its stated time. Observed power is a measurement with its own timestamp. A valid comparison requires matching times and averaging intervals.',
    },
    {
      icon: ChartNoAxesCombined,
      title: 'Expected range',
      text: 'The shaded band shows the expected range. A wider band means more uncertainty; use the range when planning.',
    },
    {
      icon: ShieldCheck,
      title: 'Forecast confidence',
      text: 'An operational indicator of data quality and system consistency. It is not a probability that the forecast is correct.',
    },
  ]
  return (
    <div className="operator-guide">
      <p className="text-sm leading-7 text-muted">
        {t(
          'Start with the station status. If attention is required, open the recommended action. Then review the next 48 hours.',
        )}
      </p>
      {items.map(({ icon: Icon, title, text }) => (
        <article key={title}>
          <Icon size={19} />
          <div>
            <h3>{t(title)}</h3>
            <p>{t(text)}</p>
          </div>
        </article>
      ))}
      <p className="guide-note">{t('Power is shown as a percentage of rated output, not energy in MWh.')}</p>
      <p className="text-xs leading-6 text-muted">
        {t(
          'All operational timestamps use UTC. Current turbine readings require a connected measurement source. Historical and outdated measurements always show their date.',
        )}
      </p>
    </div>
  )
}
