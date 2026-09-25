import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import type { OperationsSnapshot } from '../src/types/operations'
import type { MeasurementState } from '../src/types/telemetry'

const dictionaries: Record<string, Record<string, string>> = Object.fromEntries(
  ['ru', 'kk'].map((locale) => [
    locale,
    JSON.parse(readFileSync(new URL(`../src/i18n/locales/${locale}.json`, import.meta.url), 'utf8')),
  ]),
)

test('measured power, partial coverage and stale values remain distinct in all languages', async ({
  page,
  request,
}) => {
  const snapshot: OperationsSnapshot = await (await request.get('/api/operations')).json()
  expect(snapshot.forecast).not.toBeNull()
  snapshot.busy = false
  snapshot.error = null
  const telemetry = snapshot.telemetry!
  expect(telemetry).toBeTruthy()
  const now = Date.now()

  // Only this browser receives the test responses; no measurement is written to the live API.
  function setReadings(states: [MeasurementState, MeasurementState]) {
    const freshCount = states.filter((state) => state === 'fresh').length
    telemetry.available = freshCount === 2
    telemetry.freshCount = freshCount
    telemetry.status = freshCount === 2 ? 'connected' : freshCount === 1 ? 'partial' : 'stale'
    telemetry.readings = states.map((state, index) => ({
      turbineId: index === 0 ? 'WT-01' : 'WT-02',
      state,
      ageSeconds: state === 'fresh' ? 120 : 1800,
      measurement: {
        turbineId: index === 0 ? 'WT-01' : 'WT-02',
        timestamp: new Date(now - (state === 'fresh' ? 120_000 : 1_800_000)).toISOString(),
        power: index === 0 ? 0 : 0.51,
        windSpeed: 7.2,
        windDirection: 245,
        temperature: 16,
      },
    }))
    snapshot.forecast!.telemetryAvailable = telemetry.available
    snapshot.turbines = snapshot.turbines.map((turbine, index) => ({
      ...turbine,
      status: 'unknown',
      telemetryState: states[index],
      measurement: telemetry.readings[index].measurement,
      observed: states[index] === 'fresh' ? telemetry.readings[index].measurement!.power : null,
      observedAt: states[index] === 'fresh' ? telemetry.readings[index].measurement!.timestamp : null,
    }))
  }

  setReadings(['fresh', 'fresh'])
  await page.route('**/api/operations', (route) => route.fulfill({ json: snapshot }))
  await page.goto('/#twin')
  await expect(page.getByTestId('telemetry-summary')).toHaveText('Current turbine readings available')
  await expect(page.getByTestId('measurement-WT-01')).toContainText('0%')
  await expect(page.getByTestId('measurement-WT-02')).toContainText('51%')
  await expect(page.locator('.turbine-card').first()).toContainText('Not verified')

  for (const locale of ['ru', 'kk']) {
    await page.getByTestId('language-select').selectOption(locale)
    await expect(page.getByTestId('telemetry-summary')).toHaveText(
      dictionaries[locale]['Current turbine readings available'],
    )
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.screenshot({
    path: '.test-artifacts/telemetry-twin-kk.png',
    fullPage: true,
    animations: 'disabled',
  })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.getByTestId('language-select').selectOption('en')

  setReadings(['fresh', 'stale'])
  await expect(page.getByTestId('telemetry-summary')).toHaveText('Some turbine readings are unavailable')
  await expect(page.getByTestId('measurement-WT-02')).toContainText('OUT OF DATE')
  await expect(page.locator('.turbine-card').nth(1)).toContainText(
    'This reading is not available as current telemetry.',
  )

  setReadings(['stale', 'stale'])
  await expect(page.getByTestId('telemetry-summary')).toHaveText('Turbine readings are out of date')
  await expect(page.getByTestId('telemetry-status')).not.toContainText('FRESH READING')

  setReadings(['fresh', 'fresh'])
  await expect(page.getByTestId('telemetry-summary')).toHaveText('Current turbine readings available')
  await page.unroute('**/api/operations')
  await page.route('**/api/operations', (route) => route.abort())
  await expect(page.getByTestId('telemetry-summary')).toHaveText('Turbine readings need attention')
  await expect(page.getByTestId('measurement-WT-01')).toContainText('UNAVAILABLE')
  await expect(page.locator('.turbine-card').first()).not.toContainText('FRESH READING')
})

test('connection instructions are reachable from the operator briefing and fit a phone', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('operator-brief')).toContainText('Current turbine readings are not connected')
  await page.getByRole('button', { name: 'View connection details' }).click()
  await expect(page.getByTestId('telemetry-summary')).toHaveText('Current turbine readings are not connected')
  for (const locale of ['ru', 'kk']) {
    await page.getByTestId('language-select').selectOption(locale)
    const label = dictionaries[locale]['How to connect turbine readings']
    await page.locator('details summary').filter({ hasText: label }).click()
    await expect(page.locator('details')).toContainText('WINDOPS_TELEMETRY_FILE')
    await page.setViewportSize({ width: 360, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({
      path: `.test-artifacts/telemetry-setup-${locale}.png`,
      fullPage: true,
      animations: 'disabled',
    })
    await page.locator('details summary').filter({ hasText: label }).click()
  }
})
