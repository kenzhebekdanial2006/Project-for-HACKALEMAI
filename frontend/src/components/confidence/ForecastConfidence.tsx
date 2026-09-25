import { useI18n } from '../../i18n/I18nContext'
import { Info } from 'lucide-react'
import { Tooltip } from '../ui/tooltip'
import { Badge } from '../ui/shared'
import type { ConfidenceFactors } from '../../types/forecast'
export function ForecastConfidence({
  score,
  factors,
  compact = false,
}: {
  score: number
  factors?: ConfidenceFactors
  compact?: boolean
}) {
  const { t: translateText, tx } = useI18n()

  const high = score >= 85
  return (
    <div className="confidence">
      <div className="flex items-center justify-between gap-3">
        <span className={compact ? 'text-lg font-semibold' : 'metric-value'}>
          {tx(score)}
          <span className="ml-1 text-sm font-normal text-muted">/ 100</span>
        </span>
        <Tooltip
          content={
            <div className="space-y-3">
              <p className="font-medium text-white">{translateText('System confidence breakdown')}</p>
              {tx(
                Object.entries(factors || {}).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-8">
                    <span>
                      {tx(
                        {
                          weatherData: 'Weather data',
                          modelStability: 'Model stability',
                          twinConsistency: 'Twin consistency',
                          dataFreshness: 'Data freshness',
                          forecastAgreement: 'Forecast agreement',
                        }[key],
                      )}
                    </span>
                    <span className="font-mono text-white">{tx(value ?? 'Not available')}</span>
                  </div>
                )),
              )}
              <p className="max-w-60 border-t border-white/10 pt-3 text-[11px] leading-relaxed">
                {translateText(
                  'An operational indicator of data quality and system consistency. It is not a probability that the forecast is correct.',
                )}
              </p>
            </div>
          }
        >
          <button
            aria-label={translateText('Forecast confidence breakdown')}
            className="flex items-center gap-1.5"
          >
            <Badge tone={high ? 'green' : 'amber'}>
              {tx(high ? 'HIGH' : score >= 60 ? 'MEDIUM' : 'LOW')}
            </Badge>
            <Info size={12} className="text-muted" />
          </button>
        </Tooltip>
      </div>
      <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className={`h-full rounded-full transition-all duration-1000 ${high ? 'bg-[#79deb0]' : 'bg-[#e9b763]'}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  )
}
