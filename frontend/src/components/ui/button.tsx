import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-xs font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-300',
  {
    variants: {
      variant: {
        default: 'bg-[#86e8bb] text-[#10271d] hover:bg-[#a3f2ce]',
        outline: 'border border-[#2a343e] bg-[#141c24] text-[#c6cdd4] hover:bg-[#202b35]',
        ghost: 'text-[#919ba7] hover:bg-[#202a34] hover:text-white',
      },
      size: { default: 'h-9 px-3.5', sm: 'h-8 px-3', icon: 'h-9 w-9' },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)
export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean
}
export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : 'button'
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />
}
