import { Languages } from 'lucide-react'
import { useId } from 'react'
import { useI18n } from '../../i18n/I18nContext'
import { localeNames, type Locale } from '../../i18n/translate'

export function LanguageSelector({ expanded = false }: { expanded?: boolean }) {
  const { locale, setLocale, t } = useI18n()
  const id = useId()
  return (
    <div className={`language-selector ${expanded ? 'expanded' : ''}`}>
      <Languages size={15} aria-hidden="true" />
      {expanded && <label htmlFor={id}>{t('Interface language')}</label>}
      <select
        id={id}
        aria-label={t('Interface language')}
        data-testid={expanded ? 'settings-language' : 'language-select'}
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
      >
        {(['en', 'ru', 'kk'] as const).map((language) => (
          <option key={language} value={language} lang={language}>
            {localeNames[language]}
          </option>
        ))}
      </select>
    </div>
  )
}
