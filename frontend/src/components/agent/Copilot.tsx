import { useI18n } from '../../i18n/I18nContext'
import { useEffect, useRef, useState } from 'react'
import { ArrowUp, ArrowUpRight, Bot, LoaderCircle, MessageSquare, Sparkles } from 'lucide-react'
import { useOperations } from '../../state/OperationsContext'
import { copilotService } from '../../services/api'
import { Dialog } from '../ui/dialog'
import { Button } from '../ui/button'
import type { CopilotHistoryItem, CopilotResponse } from '../../types/copilot'
interface Message extends CopilotResponse {
  question: string
}
const suggestedQuestions = [
  'Why does generation decrease tomorrow?',
  'When is peak generation expected?',
  'Compare WT-01 and WT-02',
  'What changed since the previous forecast?',
  'Are there any anomalies?',
  'Why is forecast confidence lower?',
]
export function Copilot() {
  const { t: translateText, tx, locale } = useI18n()

  const { forecast, setPage } = useOperations()
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const activeForecast = useRef(forecast?.id)
  useEffect(() => {
    activeForecast.current = forecast?.id
    setMessages([])
    setError('')
  }, [forecast?.id])
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages])
  const ask = async (question: string) => {
    if (!forecast || !question.trim() || sending) return
    setSending(true)
    setError('')
    try {
      const history: CopilotHistoryItem[] = messages.slice(-6).flatMap((message) => [
        { role: 'user', content: message.question.slice(0, 4000) },
        { role: 'assistant', content: message.answer.slice(0, 4000) },
      ])
      const response = await copilotService.ask(question.trim(), locale, history, forecast.id)
      if (response.forecastId !== activeForecast.current) {
        setError('The forecast changed. Ask again using the latest data.')
        return
      }
      setMessages((m) => [...m, { question: question.trim(), ...response }])
      setInput('')
    } catch (error) {
      setError(error instanceof Error ? error.message : 'The assistant is temporarily unavailable.')
    } finally {
      setSending(false)
    }
  }
  return (
    <>
      <button className="copilot-trigger" onClick={() => setOpen(true)}>
        <Sparkles size={16} />
        <span>{translateText('Ask WindOps AI')}</span>
        <span className="copilot-key">
          <MessageSquare size={12} />
        </span>
      </button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={translateText('WindOps Copilot')}
        description={translateText('Operational clarity, grounded in your forecast.')}
        drawer
      >
        <div className="copilot-intro">
          <div className="agent-orb small">
            <Bot size={23} />
          </div>
          <h3>{translateText('What would you like to understand?')}</h3>
          <p>{translateText('Explore your forecast and turbine behaviour.')}</p>
        </div>
        <div className="space-y-2">
          {tx(
            suggestedQuestions.map((q) => (
              <button
                className="suggested-question"
                key={q}
                disabled={sending || !forecast}
                onClick={() => void ask(translateText(q))}
              >
                {tx(q)}
                <ArrowUpRight size={13} />
              </button>
            )),
          )}
        </div>
        <div className="mt-6 space-y-5" aria-live="polite">
          {tx(
            messages.map((m, i) => (
              <div key={i}>
                <p className="mb-3 rounded-lg bg-white/5 p-3 text-sm">{m.question}</p>
                <div className="border-l-2 border-emerald-300/40 pl-4">
                  <span className="mb-2 flex items-center gap-1.5 text-[10px] font-medium text-emerald-300">
                    <Sparkles size={11} />
                    {translateText('WINDOPS AI')}
                    <span className="ml-auto text-muted" data-testid="copilot-provider">{translateText(m.provider)}</span>
                  </span>
                  <p className="whitespace-pre-line text-xs leading-6 text-[#a8b5c0]" data-testid="copilot-answer">{tx(m.answer)}</p>
                  {m.notice && <p role="status" className="mt-2 text-xs leading-5 text-amber-300">{translateText(m.notice)}</p>}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {tx(
                      m.references.map((r) => (
                        <button
                          className="reference-link"
                          key={r}
                          onClick={() => {
                            setPage(
                              r === 'Diagnostics'
                                ? 'diagnostics'
                                : r === 'Twin comparison' || r === 'Current turbine readings'
                                  ? 'twin'
                                  : r === 'Agent event log'
                                    ? 'agent'
                                    : 'forecast',
                            )
                            setOpen(false)
                          }}
                        >
                          {tx(r)}
                          <ArrowUpRight size={10} />
                        </button>
                      )),
                    )}
                  </div>
                </div>
              </div>
            )),
          )}
          <div ref={end} />
        </div>
        <form
          className="copilot-input"
          onSubmit={(e) => {
            e.preventDefault()
            void ask(input)
          }}
        >
          <input
            aria-label={translateText('Ask WindOps AI')}
            placeholder={translateText('Ask about your wind farm…')}
            value={input}
            maxLength={2000}
            onChange={(e) => setInput(e.target.value)}
          />
          <Button
            size="icon"
            disabled={!input.trim() || !forecast || sending}
            aria-label={translateText('Send question')}
          >
            {sending ? <LoaderCircle size={17} className="animate-spin" /> : <ArrowUp size={17} />}
          </Button>
        </form>
        {sending && <p role="status" className="mt-3 text-xs text-muted">{translateText('Thinking about the forecast…')}</p>}
        {error && (
          <p className="mt-3 text-xs text-amber-300" role="alert">
            {translateText(error)}
          </p>
        )}
        <p className="mt-3 text-center text-[10px] text-muted">
          {translateText(
            'Answers use the published forecast and available measurements with their timestamps.',
          )}
        </p>
      </Dialog>
    </>
  )
}
