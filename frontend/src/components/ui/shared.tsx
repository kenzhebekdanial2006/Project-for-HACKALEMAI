import { useI18n } from '../../i18n/I18nContext'
import type { ReactNode } from 'react'
import { ArrowUpRight, Check, LoaderCircle } from 'lucide-react'
import { cn } from '../../lib/utils'
export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  const { tx } = useI18n()

  return <section className={cn('panel', className)}>{tx(children)}</section>
}
export function PanelHeading({
  title,
  subtitle,
  action,
  icon,
}: {
  title: string
  subtitle?: string
  action?: ReactNode
  icon?: ReactNode
}) {
  const { tx } = useI18n()

  return (
    <div className="panel-heading">
      <div>
        <h2 className="flex items-center gap-2 text-[13px] font-semibold text-[#e2e8ee]">
          {tx(icon)}
          {tx(title)}
        </h2>
        {tx(subtitle && <p className="mt-1.5 text-[11px] text-muted">{tx(subtitle)}</p>)}
      </div>
      {tx(action)}
    </div>
  )
}
export function Badge({
  children,
  tone = 'green',
  dot = false,
}: {
  children: ReactNode
  tone?: 'green' | 'amber' | 'blue' | 'gray' | 'red'
  dot?: boolean
}) {
  const { tx } = useI18n()

  return (
    <span className={cn('badge', `badge-${tone}`)}>
      {tx(dot && <span className="status-dot" />)}
      {tx(children)}
    </span>
  )
}
export function TextLink({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  const { tx } = useI18n()

  return (
    <button
      className="inline-flex items-center gap-1 text-[11px] text-muted transition-colors hover:text-[#8debbf]"
      onClick={onClick}
    >
      {tx(children)}
      <ArrowUpRight size={13} />
    </button>
  )
}
export function LoadingState({ label = 'Receiving weather data…' }: { label?: string }) {
  const { tx } = useI18n()

  return (
    <div role="status" className="space-y-5">
      <div className="flex items-center gap-3 text-sm text-emerald-300">
        <LoaderCircle size={18} className="animate-spin" />
        {tx(label)}
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {tx([1, 2, 3, 4].map((i) => <div key={i} className="h-28 animate-pulse rounded-xl bg-[#17222c]" />))}
      </div>
      <div className="h-80 animate-pulse rounded-xl bg-[#17222c]" />
    </div>
  )
}
export function CheckLine({ children }: { children: ReactNode }) {
  const { tx } = useI18n()

  return (
    <span className="flex items-center gap-2 text-xs text-muted">
      <Check size={13} className="text-emerald-300" />
      {tx(children)}
    </span>
  )
}
