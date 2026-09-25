import { useI18n } from '../../i18n/I18nContext'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ForecastRecord } from '../../types/forecast'
import { timeLabel } from '../../lib/utils'
export type WindKey = 'windSpeed10m' | 'windSpeed80m' | 'windSpeed120m'
export const windSeries: { key: WindKey; label: string; color: string }[] = [
  { key: 'windSpeed10m', label: '10m', color: '#7184a0' },
  { key: 'windSpeed80m', label: '80m', color: '#6bb8ed' },
  { key: 'windSpeed120m', label: '120m', color: '#87e4b8' },
]
export function WindChart({ records, selected }: { records: ForecastRecord[]; selected: WindKey[] }) {
  const { t: translateText, tx } = useI18n()

  return (
    <div className="h-52 w-full min-w-0">
      <ResponsiveContainer>
        <LineChart data={records} margin={{ top: 8, right: 12, bottom: 0, left: -20 }}>
          <CartesianGrid vertical={false} stroke="#253039" strokeDasharray="3 5" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={timeLabel}
            minTickGap={65}
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#778692', fontSize: 10 }}
          />
          <YAxis
            unit={translateText(' m/s')}
            tick={{ fill: '#778692', fontSize: 9 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            labelFormatter={(v) => `${timeLabel(String(v))} UTC`}
            contentStyle={{
              background: '#14212b',
              border: '1px solid #35444e',
              borderRadius: 10,
              fontSize: 11,
            }}
            formatter={(value: number, name: string) => [
              translateText(`${value.toFixed(1)} m/s`),
              translateText(name),
            ]}
          />
          {tx(
            windSeries
              .filter((s) => selected.includes(s.key))
              .map((s) => (
                <Line
                  key={s.key}
                  name={translateText(`Wind ${s.label}`)}
                  dataKey={s.key}
                  stroke={s.color}
                  dot={false}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              )),
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
