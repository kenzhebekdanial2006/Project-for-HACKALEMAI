import { describe, expect, it } from 'vitest'
import ru from './locales/ru.json'
import kk from './locales/kk.json'
import { detectLocale, translate } from './translate'
import { formatDate, formatNumber } from './format'
describe('Operator localization', () => {
  it('formats Kazakh dates and numbers without incomplete browser locale fallbacks', () => {
    expect(formatDate('2026-02-03T08:00:00Z', 'kk')).toBe('03 ақп.')
    expect(
      formatDate('2026-09-23T23:00:00Z', 'kk', { day: '2-digit', month: 'short', year: 'numeric' }),
    ).toBe('23 қыр. 2026')
    expect(formatNumber(18.28, 'kk', 2)).toBe('18,28')
  })
  it('provides both translations and preserves every placeholder', () => {
    expect(Object.keys(ru).sort()).toEqual(Object.keys(kk).sort())
    for (const dictionary of [ru, kk])
      for (const [source, target] of Object.entries(dictionary)) {
        expect(target.trim(), source).not.toBe('')
        expect((target.match(/\{\d+\}/g) || []).sort(), source).toEqual(
          (source.match(/\{\d+\}/g) || []).sort(),
        )
      }
  })
  it('prefers the saved locale, then the browser locale', () => {
    expect(detectLocale('kk', ['ru-RU'])).toBe('kk')
    expect(detectLocale(null, ['ru-KZ'])).toBe('ru')
    expect(detectLocale('invalid', ['kk-KZ'])).toBe('kk')
    expect(detectLocale(null, ['fr-FR'])).toBe('en')
  })
  it.each(['ru', 'kk'] as const)(
    'translates actual backend messages in %s without changing numbers',
    (locale) => {
      const messages = [
        'System confidence: 74/100. Unavailable checks are disclosed.',
        '48-hour forecast published. System confidence: 74/100.',
        'Next-hour expected power: WT-01 62%, WT-02 59%. Current power telemetry is not connected. Historical readings cannot establish the current operating state or a current anomaly.',
      ]
      for (const message of messages) {
        const result = translate(message, locale)
        expect(result).not.toBe(message)
        expect(result.match(/\d+/g)).toEqual(message.match(/\d+/g))
        expect(result).not.toMatch(/\{\d+\}|expected|confidence|telemetry/)
      }
    },
  )
  it('keeps identifiers and whitespace intact', () => {
    expect(translate('WT-02', 'ru')).toBe('WT-02')
    expect(translate('14:42', 'kk')).toBe('14:42')
    expect(translate(' ', 'ru')).toBe(' ')
  })
  it.each(['ru', 'kk'] as const)('translates telemetry states and measured power in %s', (locale) => {
    const answer =
      'Current measurements: WT-01 0% at 2026-09-23T12:00:00Z; WT-02 Unavailable at Unavailable. Receiving measurements alone does not confirm normal operation or an anomaly. Compare power only for matching times and averaging intervals.'
    const translated = translate(answer, locale)
    expect(translated).toContain('WT-01')
    expect(translated).toContain('0%')
    expect(translated).not.toMatch(/Current measurements|Unavailable|Receiving|\{\d+\}/)
    for (const label of [
      'Current turbine readings are not connected',
      'Some turbine readings are unavailable',
      'Turbine readings are out of date',
      'FRESH READING',
      'Wind',
      'WAITING',
    ]) {
      expect(translate(label, locale)).not.toBe(label)
      expect(translate(label, locale)).not.toMatch(/^\?+$/)
    }
  })
})
