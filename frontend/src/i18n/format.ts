import type { Locale } from './translate'

const kazakhMonths = [
  'қаң.',
  'ақп.',
  'нау.',
  'сәу.',
  'мам.',
  'мау.',
  'шіл.',
  'там.',
  'қыр.',
  'қаз.',
  'қар.',
  'жел.',
]
export function formatDate(
  value: string | Date,
  locale: Locale,
  options: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short' },
): string {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return '—'
  // Some Windows browsers return synthetic M01/M02 month names for kk-KZ.
  if (locale === 'kk') {
    const parts: string[] = []
    if (options.day)
      parts.push(
        options.day === '2-digit' ? String(date.getUTCDate()).padStart(2, '0') : String(date.getUTCDate()),
      )
    if (options.month) parts.push(kazakhMonths[date.getUTCMonth()])
    if (options.year) parts.push(String(date.getUTCFullYear()))
    return parts.join(' ')
  }
  return date.toLocaleDateString(locale === 'ru' ? 'ru-RU' : 'en-GB', { ...options, timeZone: 'UTC' })
}
export function formatNumber(value: number, locale: Locale, digits = 1): string {
  return new Intl.NumberFormat(locale === 'en' ? 'en-GB' : 'ru-RU', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}
