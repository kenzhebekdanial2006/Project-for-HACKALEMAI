import { useI18n } from './i18n/I18nContext'
import { lazy, Suspense, useEffect, useState } from 'react'
import { AnimatePresence, motion, MotionConfig } from 'framer-motion'
import { OperationsProvider, useOperations } from './state/OperationsContext'
import { Sidebar } from './components/layout/Sidebar'
import { Header } from './components/layout/Header'
import { PageHeading } from './components/layout/PageHeading'
import { Copilot } from './components/agent/Copilot'
import { LoadingState } from './components/ui/shared'
import { Button } from './components/ui/button'
const Overview = lazy(() => import('./pages/Overview'))
const Forecast = lazy(() => import('./pages/Forecast'))
const TurbineTwin = lazy(() => import('./pages/TurbineTwin'))
const Agent = lazy(() => import('./pages/Agent'))
const HistoricalReplay = lazy(() => import('./pages/HistoricalReplay'))
const Diagnostics = lazy(() => import('./pages/Diagnostics'))
const pages = {
  overview: {
    component: Overview,
    title: 'Operations overview',
    description: 'Your wind farm. One clear view.',
  },
  forecast: {
    component: Forecast,
    title: '48-hour forecast',
    description: 'See what’s ahead. Understand the conditions behind every prediction.',
  },
  twin: {
    component: TurbineTwin,
    title: 'Digital Twin Comparison',
    description: 'Compare turbine behaviour under similar environmental conditions.',
  },
  agent: {
    component: Agent,
    title: 'AI Agent Control Center',
    description: 'Autonomous monitoring, transparent decisions, continuous operations.',
  },
  replay: {
    component: HistoricalReplay,
    title: 'Historical Replay',
    description: 'Recalculate forecasts using archived weather and a checked model training cutoff.',
  },
  diagnostics: {
    component: Diagnostics,
    title: 'System diagnostics',
    description: 'Data health, model configuration, and validation transparency.',
  },
}
function Workspace() {
  const { t: translateText, tx } = useI18n()

  const { page, loading, error, refresh, busy, forecast } = useOperations()
  const [menu, setMenu] = useState(false)
  const Page = pages[page].component
  useEffect(() => {
    document.documentElement.classList.toggle(
      'reduce-motion',
      localStorage.getItem('windops-reduced-motion') === 'true',
    )
  }, [])
  useEffect(() => {
    document.title = `${translateText(pages[page].title)} · WindOps AI`
  }, [page, translateText])
  return (
    <MotionConfig reducedMotion="user">
      <div className="app-shell">
        <a className="skip-link" href="#main-content">
          {translateText('Skip to main content')}
        </a>
        <Sidebar open={menu} onClose={() => setMenu(false)} />
        <div className="workspace">
          <Header onMenu={() => setMenu(true)} />
          <main id="main-content">
            <PageHeading
              title={translateText(pages[page].title)}
              description={translateText(pages[page].description)}
            />
            {tx(
              error && (
                <div role="alert" className="warning-banner mb-5">
                  <p>{tx(error)}</p>
                  <Button onClick={() => void refresh()} disabled={busy} variant="outline">
                    {translateText('Try again')}
                  </Button>
                </div>
              ),
            )}
            {tx(
              loading ? (
                <LoadingState />
              ) : ['overview', 'forecast', 'twin'].includes(page) && !forecast?.records.length ? (
                <div className="replay-empty" role="status">
                  <p>{translateText('No forecast available yet.')}</p>
                  <span>{translateText('The agent needs weather data to prepare the next forecast.')}</span>
                  <Button onClick={() => void refresh()} disabled={busy} variant="outline">
                    {tx(busy ? 'Preparing forecast…' : 'Refresh Forecast')}
                  </Button>
                </div>
              ) : (
                <AnimatePresence mode="wait">
                  <motion.div
                    key={page}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.16 }}
                  >
                    <Suspense fallback={<LoadingState label="Preparing workspace…" />}>
                      <Page />
                    </Suspense>
                  </motion.div>
                </AnimatePresence>
              ),
            )}
          </main>
        </div>
        <Copilot />
      </div>
    </MotionConfig>
  )
}
export default function App() {
  return (
    <OperationsProvider>
      <Workspace />
    </OperationsProvider>
  )
}
