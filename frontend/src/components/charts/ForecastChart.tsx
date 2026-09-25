import { useI18n } from '../../i18n/I18nContext'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ForecastRecord } from '../../types/forecast'
import { percent, timeLabel } from '../../lib/utils'
import { MousePointer2 } from 'lucide-react'

export function ForecastChart({
  records,
  height = 245,
  turbine = 'both',
  onSelect,
  historical = false,
}: {
  records: ForecastRecord[]
  height?: number
  turbine?: 'both' | 'WT01' | 'WT02'
  onSelect?: (record: ForecastRecord) => void
  historical?: boolean
}) {
  const { t: translateText, tx, dateLabel } = useI18n()

  const data = records.map((r, i) => ({
    ...r,
    hour: i,
    p1: r.WT01.prediction * 100,
    p2: r.WT02.prediction * 100,
    range1: [r.WT01.lower * 100, r.WT01.upper * 100],
    range2: [r.WT02.lower * 100, r.WT02.upper * 100],
  }))
  const nextDay = records.findIndex((r, i) => i > 0 && timeLabel(r.timestamp) === '00:00')
  return (
    <div className="forecast-chart">
      <div className="mb-4 flex items-center justify-between px-1 text-[9px] text-muted">
        <span>{translateText('NORMALIZED POWER (%)')}</span>
        <span className="flex items-center gap-1.5">
          {tx(
            onSelect && (
              <>
                <MousePointer2 size={11} />
                {translateText('Click a point to explore')}
              </>
            ),
          )}
        </span>
      </div>
      <div className="mb-1 ml-9 text-[8px] tracking-wider text-muted">
        {dateLabel(records[0].timestamp).toUpperCase()}
      </div>
      <div style={{ width: '100%', height, minWidth: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            margin={{ top: 15, right: 10, bottom: 2, left: -26 }}
            onClick={(state) => {
              if (state?.activePayload?.[0]?.payload && onSelect)
                onSelect(state.activePayload[0].payload as ForecastRecord)
            }}
          >
            <CartesianGrid stroke="#253039" strokeDasharray="3 5" vertical={false} />
            <XAxis
              dataKey="hour"
              type="number"
              domain={[0, records.length - 1]}
              ticks={records.length <= 24 ? [0, 4, 8, 12, 16, 20, 23] : [0, 6, 12, 18, 24, 30, 36, 42, 47]}
              tickFormatter={(h) => (records[h] ? timeLabel(records[h].timestamp) : '')}
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#778692', fontSize: 10 }}
              dy={10}
            />
            <YAxis
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tickFormatter={(v) => `${v}`}
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#778692', fontSize: 10 }}
            />
            <Tooltip
              cursor={{ stroke: '#78938e', strokeDasharray: '3 4' }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const r = payload[0].payload as ForecastRecord
                return (
                  <div className="chart-tooltip">
                    <p className="mb-3 border-b border-white/10 pb-2 text-xs font-semibold">
                      {tx(dateLabel(r.timestamp))} · {tx(timeLabel(r.timestamp))}
                      {translateText(' UTC')}
                    </p>
                    {tx(
                      (['WT01', 'WT02'] as const)
                        .filter((key) => turbine === 'both' || turbine === key)
                        .map((key) => (
                          <div key={key} className="mb-3">
                            <p className={key === 'WT01' ? 'text-emerald-300' : 'text-sky-300'}>
                              {tx(key === 'WT01' ? 'WT-01' : 'WT-02')}
                            </p>
                            <div className="tooltip-row">
                              <span>{translateText('Expected power')}</span>
                              <b>{tx(percent(r[key].prediction))}</b>
                            </div>
                            <div className="tooltip-row">
                              <span>{translateText('Expected range')}</span>
                              <b>
                                {tx(percent(r[key].lower))}–{tx(percent(r[key].upper))}
                              </b>
                            </div>
                          </div>
                        )),
                    )}
                    <div className="space-y-1 border-t border-white/10 pt-2">
                      {tx(
                        [
                          ['Wind 120m', `${r.windSpeed120m} m/s`],
                          ['Wind direction', `${r.windDirection}°`],
                          ['Gusts', `${r.gusts} m/s`],
                          ['Temperature', `${r.temperature}°C`],
                        ].map(([label, value]) => (
                          <div key={label} className="tooltip-row">
                            <span>{tx(label)}</span>
                            <b>{tx(value)}</b>
                          </div>
                        )),
                      )}
                    </div>
                  </div>
                )
              }}
            />
            {tx(
              turbine !== 'WT02' && (
                <Area
                  type="monotone"
                  dataKey="range1"
                  stroke="none"
                  fill="#7be4b5"
                  fillOpacity={0.11}
                  isAnimationActive={false}
                  tooltipType="none"
                />
              ),
            )}
            {tx(
              turbine !== 'WT01' && (
                <Area
                  type="monotone"
                  dataKey="range2"
                  stroke="none"
                  fill="#68b8ef"
                  fillOpacity={0.08}
                  isAnimationActive={false}
                  tooltipType="none"
                />
              ),
            )}
            {tx(
              nextDay > 0 && (
                <ReferenceLine
                  x={nextDay}
                  stroke="#48535b"
                  strokeDasharray="3 5"
                  label={{
                    value: dateLabel(records[nextDay].timestamp).toUpperCase(),
                    fill: '#65737e',
                    fontSize: 8,
                    position: 'insideTopRight',
                  }}
                />
              ),
            )}
            <ReferenceLine
              x={0}
              stroke="#74d6ab"
              strokeDasharray="3 4"
              label={{
                value: translateText(historical ? 'ARCHIVE START' : 'FORECAST START'),
                fill: '#89d5b3',
                fontSize: 8,
                position: 'insideTopLeft',
                offset: 8,
              }}
            />
            {tx(
              turbine !== 'WT02' && (
                <Line
                  name="WT-01"
                  type="monotone"
                  dataKey="p1"
                  stroke="#89e8b9"
                  strokeWidth={2.3}
                  dot={false}
                  activeDot={{ r: 5, stroke: '#11261f', strokeWidth: 3 }}
                  isAnimationActive={false}
                />
              ),
            )}
            {tx(
              turbine !== 'WT01' && (
                <Line
                  name="WT-02"
                  type="monotone"
                  dataKey="p2"
                  stroke="#67b6eb"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={false}
                  activeDot={{ r: 5 }}
                  isAnimationActive={false}
                />
              ),
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-bottom">
        <div className="flex flex-wrap items-center gap-4">
          <span hidden={turbine === 'WT02'}>
            <i className="legend-line bg-[#89e8b9]" />
            {translateText('WT-01')}
          </span>
          <span hidden={turbine === 'WT01'}>
            <i className="legend-line bg-[#67b6eb]" />
            {translateText('WT-02')}
          </span>
          <span>
            <i className="legend-band" />
            {translateText('Expected range')}
          </span>
        </div>
        <span>{translateText('All times UTC')}</span>
      </div>
    </div>
  )
}
