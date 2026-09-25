import { useI18n } from '../../i18n/I18nContext'
import { useId } from 'react'
export function TurbineVisual({
  warning = false,
  landscape = false,
}: {
  warning?: boolean
  landscape?: boolean
}) {
  const { t: translateText, tx } = useI18n()

  const id = useId().replace(/:/g, '')
  const color = warning ? '#e7b463' : '#83e4b7'
  return (
    <svg
      viewBox={landscape ? '0 0 420 168' : '0 0 150 150'}
      aria-label={translateText('Wind turbine digital twin')}
      role="img"
      className={landscape ? 'farm-visual' : 'turbine-visual'}
    >
      <defs>
        <linearGradient id={`tower-${id}`} x1="0" x2="1">
          <stop stopColor="#384f51" />
          <stop offset=".5" stopColor="#b4c9c9" />
          <stop offset="1" stopColor="#50676b" />
        </linearGradient>
        <radialGradient id={`glow-${id}`}>
          <stop stopColor={color} stopOpacity=".14" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </radialGradient>
        <pattern id={`grid-${id}`} width="24" height="24" patternUnits="userSpaceOnUse">
          <path d="M 24 0 L 0 0 0 24" fill="none" stroke="#57767c" strokeWidth=".4" strokeOpacity=".25" />
        </pattern>
      </defs>
      {tx(
        landscape && (
          <>
            <rect width="420" height="168" fill={`url(#grid-${id})`} />
            <ellipse cx="210" cy="130" rx="185" ry="40" fill={`url(#glow-${id})`} />
            <path d="M0 137 Q80 115 145 133 T280 129 T420 133" stroke="#2e4645" fill="none" />
            <path d="M0 145 Q100 135 200 143 T420 140" stroke="#253733" fill="none" />
          </>
        ),
      )}
      {tx(
        (landscape
          ? [
              { x: 133, y: 20, s: 0.85 },
              { x: 253, y: 37, s: 0.69 },
            ]
          : [{ x: 0, y: 0, s: 1 }]
        ).map((t, i) => (
          <g key={i} transform={`translate(${t.x} ${t.y}) scale(${t.s})`}>
            <ellipse cx="75" cy="137" rx="34" ry="8" fill={`url(#glow-${id})`} />
            <path d="M72 58 68 136 Q75 141 82 136 L78 58Z" fill={`url(#tower-${id})`} />
            <path d="M75 65v65" stroke="#d2e8e1" strokeOpacity=".24" />
            <g
              className="turbine-rotor"
              style={{ transformOrigin: '75px 54px', animationDuration: `${warning ? 38 : 24 + i * 5}s` }}
            >
              <path d="M75 54 71 43 73 6 Q75 0 77 7L79 42Z" fill="#a7c2bd" />
              <path d="m75 54 12 2 31 22q5 5-2 4L81 63Z" fill="#789792" />
              <path d="m75 54-6 11-31 22q-7 2-4-4L65 53Z" fill="#91aaa7" />
            </g>
            <circle cx="75" cy="54" r="5" fill="#d4ece2" />
            <circle cx="75" cy="54" r="2" fill={color} />
            <path d="M88 109h14m-8-7 8 7-8 7" stroke={color} strokeWidth="1" opacity=".6" fill="none" />
            {tx(
              landscape && (
                <text x="75" y="158" fill="#8daba4" fontSize="10" textAnchor="middle" fontFamily="monospace">
                  {translateText('WT-0')}
                  {tx(i + 1)}
                </text>
              ),
            )}
          </g>
        )),
      )}
    </svg>
  )
}
