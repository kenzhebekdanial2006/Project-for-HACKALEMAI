import { useI18n } from '../../i18n/I18nContext'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  drawer = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
  drawer?: boolean
}) {
  const { t: translateText, tx } = useI18n()

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/65 backdrop-blur-sm" />
        <DialogPrimitive.Content
          className={cn(
            'dialog-content fixed z-50 border border-[#2b3741] bg-[#111920] p-6 shadow-2xl focus:outline-none',
            drawer
              ? 'right-0 top-0 h-dvh w-full max-w-[460px] overflow-y-auto'
              : 'left-1/2 top-1/2 max-h-[90dvh] w-[calc(100%-32px)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl',
          )}
        >
          <DialogPrimitive.Title className="pr-8 text-xl font-semibold text-white">
            {tx(title)}
          </DialogPrimitive.Title>
          <DialogPrimitive.Description
            className={cn('mt-2 text-sm text-[#8593a1]', !description && 'sr-only')}
          >
            {tx(description || title)}
          </DialogPrimitive.Description>
          <DialogPrimitive.Close
            className="absolute right-4 top-4 rounded-lg p-2 text-slate-400 hover:bg-white/5 hover:text-white"
            aria-label={translateText('Close panel')}
          >
            <X size={18} />
          </DialogPrimitive.Close>
          <div className="mt-6">{tx(children)}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
