import { useI18n } from '../../i18n/I18nContext'
import { useEffect, useState } from 'react'
import { ArrowUpRight, History, Info, LoaderCircle, Wind } from 'lucide-react'
import type { ForecastRecord } from '../../types/forecast'
import { percent, timeLabel } from '../../lib/utils'
import { explanationService } from '../../services/api'
import { Dialog } from '../ui/dialog'
import { Panel } from '../ui/shared'
import { Button } from '../ui/button'

type Explanation = Awaited<ReturnType<typeof explanationService.getExplanation>>
export function ForecastExplanation({
  record,
  onClose,
  turbine = 'WT01',
}: {
  record: ForecastRecord | null
  onClose: () => void
  turbine?: 'WT01' | 'WT02'
}) {
  const { t: translateText, tx, dateLabel } = useI18n()

  const [showPeriods, setShowPeriods] = useState(false)
  const [activeTurbine, setActiveTurbine] = useState(turbine)
  const [explanation, setExplanation] = useState<Explanation | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    setActiveTurbine(turbine)
    setShowPeriods(false)
  }, [turbine, record])
  useEffect(() => {
    let active = true
    setExplanation(null)
    setError('')
    if (record)
      explanationService
        .getExplanation(record, activeTurbine)
        .then((value) => {
          if (active) setExplanation(value)
        })
        .catch(() => {
          if (active) setError('The forecast explanation is temporarily unavailable.')
        })
    return () => {
      active = false
    }
  }, [record, activeTurbine])
  return (
    <Dialog
      open={!!record}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      title={translateText('Why this forecast?')}
      description={translateText('Understand the conditions behind the expected output.')}
      drawer
    >
      {tx(
        record && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-sm text-muted">
                {tx(dateLabel(record.timestamp))} · {tx(timeLabel(record.timestamp))}
                {translateText(' UTC')}
              </span>
              <div className="segmented">
                {tx(
                  (['WT01', 'WT02'] as const).map((t) => (
                    <button
                      key={t}
                      className={activeTurbine === t ? 'selected' : ''}
                      onClick={() => setActiveTurbine(t)}
                    >
                      {tx(t === 'WT01' ? 'WT-01' : 'WT-02')}
                    </button>
                  )),
                )}
              </div>
            </div>
            <Panel className="my-5 p-5">
              <p className="text-xs text-muted">{translateText('Expected power')}</p>
              <p className="my-2 text-4xl font-medium">{tx(percent(record[activeTurbine].prediction))}</p>
              <p className="text-xs text-muted">
                {translateText('Expected range')}
                {tx(' ')}
                <span className="text-emerald-300">
                  {tx(percent(record[activeTurbine].lower))}–{tx(percent(record[activeTurbine].upper))}
                </span>
              </p>
            </Panel>
            {tx(
              error && (
                <p role="alert" className="text-sm text-amber-300">
                  {tx(error)}
                </p>
              ),
            )}
            {tx(
              !explanation && !error && (
                <p role="status" className="flex items-center gap-2 text-xs text-muted">
                  <LoaderCircle size={14} className="animate-spin" />
                  {translateText('Loading forecast drivers…')}
                </p>
              ),
            )}
            {tx(
              explanation && (
                <>
                  <h3 className="mb-5 flex items-center gap-2 text-sm font-medium">
                    <Wind size={16} className="text-emerald-300" />
                    {translateText('Main forecast drivers')}
                  </h3>
                  <div className="space-y-5">
                    {tx(
                      explanation.drivers.map((driver) => (
                        <div key={driver.label}>
                          <div className="mb-2 flex justify-between text-xs">
                            <span>{tx(driver.label)}</span>
                            <span className="text-[10px] text-muted">{tx(driver.note)}</span>
                          </div>
                          <div className="h-1.5 rounded-full bg-white/5">
                            <div
                              className={`h-full rounded-full ${driver.negative ? 'bg-amber-300/70' : 'bg-emerald-300/70'}`}
                              style={{ width: `${driver.value}%` }}
                            />
                          </div>
                        </div>
                      )),
                    )}
                  </div>
                  <p className="mt-4 flex items-center gap-1.5 text-[10px] text-muted">
                    <Info size={11} />
                    {translateText('Contributions calculated by the trained model for this hour.')}
                  </p>
                  <div className="mt-8 border-t border-white/10 pt-6">
                    <h3 className="flex items-center gap-2 text-sm font-medium">
                      <History size={16} className="text-sky-300" />
                      {translateText('Similar historical conditions')}
                    </h3>
                    <p className="mt-2 text-xs text-muted">
                      {tx(explanation.historicalCount)}
                      {translateText(' matching historical periods')}
                    </p>
                    <div className="my-5 space-y-3 text-xs">
                      {tx(
                        [
                          ['Average historical power', percent(explanation.historicalAverage)],
                          ['Current prediction', percent(record[activeTurbine].prediction)],
                          [
                            'Historical range',
                            `${percent(explanation.historicalLower)}–${percent(explanation.historicalUpper)}`,
                          ],
                        ].map(([key, value]) => (
                          <div key={key} className="flex justify-between">
                            <span className="text-muted">{tx(key)}</span>
                            <span>{tx(value)}</span>
                          </div>
                        )),
                      )}
                    </div>
                    <Button
                      variant="outline"
                      className="w-full"
                      disabled={explanation.historicalCount === 0}
                      onClick={() => setShowPeriods((value) => !value)}
                    >
                      {tx(showPeriods ? 'Hide similar periods' : 'View similar periods')}
                      <ArrowUpRight size={14} />
                    </Button>
                    {tx(
                      showPeriods && (
                        <div className="mt-4 space-y-3 rounded-lg bg-white/[.025] p-4">
                          <p className="text-[10px] text-muted">
                            {translateText('MATCHING ARCHIVE OBSERVATIONS')}
                          </p>
                          {tx(
                            explanation.periods.map((period) => (
                              <div key={period.timestamp} className="flex justify-between text-xs">
                                <span>
                                  {tx(dateLabel(period.timestamp))} · {tx(timeLabel(period.timestamp))}
                                </span>
                                <span className="text-emerald-300">{tx(percent(period.power))}</span>
                              </div>
                            )),
                          )}
                        </div>
                      ),
                    )}
                  </div>
                  <p className="mt-4 text-xs leading-6 text-muted">
                    {translateText(explanation.matchingRule)}
                  </p>
                </>
              ),
            )}
          </>
        ),
      )}
    </Dialog>
  )
}
