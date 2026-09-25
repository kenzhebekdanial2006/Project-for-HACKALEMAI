import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { detectLocale, intlLocales, translate, type Locale } from './translate'
import { formatDate, formatNumber } from './format'

const STORAGE_KEY = 'windops-language'
function initialLocale(): Locale {
  if (typeof window === 'undefined') return 'en'
  let saved: string | null = null
  try {
    saved = localStorage.getItem(STORAGE_KEY)
  } catch {
    /* Preferences may be unavailable. */
  }
  return detectLocale(saved, navigator.languages)
}
function createFormatters(locale: Locale) {
  const t = (text: string | null | undefined) => translate(text || '', locale)
  const number = (value: number, digits = 1) => formatNumber(value, locale, digits)
  const tx = (node: ReactNode): ReactNode => {
    if (typeof node === 'string') return t(node)
    if (typeof node === 'number') return Number.isInteger(node) ? node : number(node)
    if (Array.isArray(node)) return node.map(tx)
    return node
  }
  const date = (timestamp: string | Date, options?: Intl.DateTimeFormatOptions) =>
    formatDate(timestamp, locale, options)
  const dateLabel = (timestamp: string) => date(timestamp)
  return { locale, intlLocale: intlLocales[locale], t, tx, number, dateLabel, date }
}
const I18nContext = createContext({ ...createFormatters('en'), setLocale: (_locale: Locale) => {} })
export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(initialLocale)
  useEffect(() => {
    document.documentElement.lang = locale
    try {
      localStorage.setItem(STORAGE_KEY, locale)
    } catch {
      /* Keep the in-memory selection. */
    }
  }, [locale])
  const value = useMemo(() => ({ ...createFormatters(locale), setLocale }), [locale])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}
export const useI18n = () => useContext(I18nContext)
