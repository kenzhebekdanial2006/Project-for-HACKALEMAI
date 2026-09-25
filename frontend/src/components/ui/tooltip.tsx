import { useI18n } from '../../i18n/I18nContext'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import type { ReactNode } from 'react'
export function Tooltip({ children, content }: { children: ReactNode; content: ReactNode }) {
  const { tx } = useI18n()

  return (
    <TooltipPrimitive.Provider delayDuration={150}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{tx(children)}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            sideOffset={10}
            className="z-[80] max-w-xs rounded-xl border border-[#31404c] bg-[#17222c] p-4 text-xs text-slate-300 shadow-xl"
          >
            {tx(content)}
            <TooltipPrimitive.Arrow className="fill-[#31404c]" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}
