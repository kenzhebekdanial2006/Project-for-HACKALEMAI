import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
const ru: Record<string, string> = JSON.parse(
  readFileSync(new URL('../src/i18n/locales/ru.json', import.meta.url), 'utf8'),
)
const kk: Record<string, string> = JSON.parse(
  readFileSync(new URL('../src/i18n/locales/kk.json', import.meta.url), 'utf8'),
)

test('dashboard displays predictions from the actual API and model explanations', async ({
  page,
  request,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await expect(page.locator('.kpi-grid')).toBeVisible({ timeout: 45000 })
  const snapshot = await (await request.get('/api/operations')).json()
  expect(snapshot.connected).toBe(true)
  expect(snapshot.forecast.mode).toBe('live')
  expect(snapshot.forecast.modelVersion).toBe('weather_v2')
  expect(new Date(snapshot.forecast.records[0].timestamp).getTime()).toBeGreaterThan(
    new Date(snapshot.forecast.origin).getTime(),
  )
  const average =
    snapshot.forecast.records
      .slice(0, 6)
      .reduce(
        (sum: number, row: { WT01: { prediction: number }; WT02: { prediction: number } }) =>
          sum + (row.WT01.prediction + row.WT02.prediction) / 2,
        0,
      ) / 6
  await expect(page.locator('.kpi-grid .metric-value').first()).toHaveText(`${Math.round(average * 100)}%`)
  await expect(page.getByTestId('operator-brief')).toContainText('Current turbine readings are not connected')
  await expect(page.locator('#demo-scenario')).toHaveCount(0)
  await expect(page.locator('body')).not.toContainText('DEMO')
  await page.locator('nav a[data-page="forecast"]').click()
  await expect(page.getByRole('heading', { name: 'Predicted power' })).toBeVisible()
  const chart = page.locator('.forecast-chart .recharts-wrapper').first()
  await chart.hover({ position: { x: 240, y: 150 } })
  await chart.click({ position: { x: 240, y: 150 } })
  await expect(page.getByRole('dialog')).toContainText('Contributions calculated by the trained model')
  await expect(page.getByRole('dialog')).not.toContainText('Illustrative')
  await page.getByRole('button', { name: 'Close panel' }).click()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export forecast' }).click()
  expect((await download).suggestedFilename()).toBe('windops-forecast.csv')
  expect(errors).toEqual([])
  await page.screenshot({ path: '.test-artifacts/live-forecast.png', fullPage: true })
})

test('refresh invokes real weather/model processing and reports actual events', async ({ page, request }) => {
  await page.goto('/#agent')
  await expect(page.getByRole('heading', { name: 'Agent workflow' })).toBeVisible()
  const old = (await (await request.get('/api/forecast')).json()).id
  const refresh = page.waitForResponse(
    (response) => response.url().endsWith('/api/forecast/refresh') && response.request().method() === 'POST',
  )
  await page.locator('.refresh-button').click()
  expect((await refresh).status()).toBe(202)
  await expect
    .poll(async () => (await (await request.get('/api/forecast')).json()).id, { timeout: 55000 })
    .not.toBe(old)
  await expect(page.getByRole('log')).toContainText('Weather inputs validated', { timeout: 15000 })
  await expect(page.getByRole('log')).toContainText('Current telemetry unavailable')
  await expect(
    page.getByRole('heading', { name: 'Monitoring incoming weather updates', exact: true }),
  ).toBeVisible()
  await expect(page.locator('body')).not.toContainText('Simulate')
})

test('historical replay uses real archived inputs and rejects training leakage', async ({ page }) => {
  await page.goto('/#replay')
  await expect(page.getByRole('button', { name: 'Run Historical Forecast' })).toBeVisible()
  await page.locator('input[type="date"]').fill('2026-02-03')
  await page.locator('input[type="time"]').fill('08:00')
  const result = page.waitForResponse((response) => response.url().endsWith('/api/replay'))
  await page.getByRole('button', { name: 'Run Historical Forecast' }).click()
  const body = await (await result).json()
  expect(body.forecast.records).toHaveLength(48)
  expect(body.forecast.weatherRun).toBe('2026-02-02T12:00:00Z')
  expect(body.weatherAvailableAt).toBe('2026-02-02T18:10:00Z')
  expect(body.forecast.modelVersion).toBe('weather_v2')
  await expect(page.getByText('INPUT CUTOFF CHECK PASSED ✓', { exact: true })).toBeVisible()
  await expect(page.getByRole('log')).toContainText('Model training cutoff checked')
  await page.locator('input[type="date"]').fill('2026-01-20')
  await page.getByRole('button', { name: 'Run Historical Forecast' }).click()
  await expect(page.getByRole('alert')).toContainText('precedes the model training cutoff')
  await expect(page.getByText('INPUT CUTOFF CHECK PASSED ✓', { exact: true })).toHaveCount(0)
})

test('Russian and Kazakh cover all six real-data pages and preserve language', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('.kpi-grid')).toBeVisible({ timeout: 45000 })
  for (const language of ['ru', 'kk'] as const) {
    const text = language === 'ru' ? ru : kk
    await page.getByTestId('language-select').selectOption(language)
    await expect(page.getByTestId('operator-brief')).toContainText(
      text['Current turbine readings are not connected'],
    )
    for (const [route, title] of [
      ['forecast', 'Predicted power'],
      ['twin', 'AI Twin Analysis'],
      ['agent', 'Agent workflow'],
      ['diagnostics', 'Validation metrics'],
      ['replay', 'Replay provenance'],
    ]) {
      await page.locator(`nav a[data-page="${route}"]`).click()
      await expect(page.getByRole('heading', { name: text[title], exact: true })).toBeVisible()
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `${language}:${route}`,
      ).toBe(true)
    }
    await page.locator('nav a[data-page="overview"]').click()
    await page.reload()
    await expect(page.getByTestId('language-select')).toHaveValue(language)
    await expect(page.locator('.kpi-grid')).toBeVisible()
  }
  await page.locator('.copilot-trigger').click()
  await page.getByRole('textbox', { name: kk['Ask WindOps AI'] }).fill('Ауытқулар бар ма?')
  await page.getByRole('button', { name: kk['Send question'] }).click()
  await expect(page.getByRole('dialog')).toContainText('Ағымдағы қуат телеметриясы қосылмаған')
  await page.getByRole('button', { name: kk['Close panel'] }).click()
  await page.getByTestId('language-select').selectOption('ru')
  await page.locator('.copilot-trigger').click()
  await expect(page.getByRole('dialog')).toContainText('Текущая телеметрия мощности не подключена')
})

test('mobile and desktop layouts fit real translated data', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.locator('.kpi-grid')).toBeVisible({ timeout: 45000 })
  for (const language of ['ru', 'kk']) {
    await page.getByTestId('language-select').selectOption(language)
    for (const route of ['overview', 'forecast', 'twin', 'agent', 'replay', 'diagnostics']) {
      await page.locator('.menu-toggle').click()
      await page.locator(`nav a[data-page="${route}"]`).click()
      await expect(page.locator('h1')).toBeVisible()
      await expect(page.locator('.sidebar')).not.toHaveClass(/sidebar-open/)
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `${language}:${route}`,
      ).toBe(true)
    }
  }
  await page.locator('.menu-toggle').click()
  await page.locator('nav a[data-page="overview"]').click()
  await expect(page.getByTestId('operator-brief')).toBeVisible()
  await expect
    .poll(async () => page.locator('.sidebar').evaluate((element) => element.getBoundingClientRect().right))
    .toBeLessThanOrEqual(0)
  await page.screenshot({
    path: '.test-artifacts/live-mobile-kk.png',
    fullPage: true,
    animations: 'disabled',
  })
  for (const width of [360, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), String(width)).toBe(
      true,
    )
  }
  await page.getByTestId('language-select').selectOption('ru')
  await page.screenshot({ path: '.test-artifacts/live-overview-ru.png', fullPage: true })
})

test('API disconnection is explicit and never becomes a synthetic forecast', async ({ page }) => {
  await page.route('**/api/operations', (route) => route.abort())
  await page.goto('/')
  await expect(page.getByRole('alert')).toContainText('Cannot connect to the operations API')
  await expect(page.locator('.kpi-grid')).toHaveCount(0)
  await expect(page.getByText('No forecast available yet.')).toBeVisible()
  await page.unroute('**/api/operations')
  await expect(page.locator('.kpi-grid')).toBeVisible({ timeout: 15000 })
})
