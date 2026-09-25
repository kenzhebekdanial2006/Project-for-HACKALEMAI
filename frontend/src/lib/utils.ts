import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs))
export const percent = (value: number | null) => (value === null ? '—' : `${Math.round(value * 100)}%`)
export const timeLabel = (timestamp: string) =>
  new Date(timestamp).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })
export const dateLabel = (timestamp: string) =>
  new Date(timestamp).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' })
