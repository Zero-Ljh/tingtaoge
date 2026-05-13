import { useState, useEffect, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'

export default function Discussion({ sessionId, mode, topic, onBack }) {
  const [agents, setAgents] = useState([])
  const [cards, setCards] = useState({})
  const [status, setStatus] = useState('连接中...')
  const [report, setReport] = useState(null)
  const [userTurn, setUserTurn] = useState(false)
  const [userFinal, setUserFinal] = useState(false)
  const [paused, setPaused] = useState(false)
  const [suggestions, setSuggestions] = useState(null)
  const [round, setRound] = useState(0)
  const [totalRounds, setTotalRounds] = useState(0)
  const [phase, setPhase] = useState('')
  const userMsgRef = useRef(null)
  const scrollRef = useRef(null)
  const isExploring = mode === 'direction_explore'

  // SSE
  useEffect(() => {
    if (!sessionId) return
    const es = new EventSource(`/api/stream/${sessionId}`)
    setCards({}); setReport(null); setUserTurn(false); setPaused(false)
    setSuggestions(null); setRound(0)

    es.onmessage = (e) => {
      try { handleEvent(JSON.parse(e.data)) } catch {}
    }
    es.onerror = () => { setStatus('连接断开'); es.close() }
    return () => es.close()
  }, [sessionId])

  const handleEvent = useCallback((data) => {
    switch (data.type) {
      case 'status':
        setStatus(data.message)
        if (data.agents) setAgents(data.agents)
        break
      case 'round_start':
        setRound(data.round); setTotalRounds(data.total)
        if (data.phase) setPhase(data.phase)
        break
      case 'agent_start':
        setCards((p) => ({
          ...p, [data.agent_id]: {
            name: data.agent_name, color: data.color, emoji: data.emoji || '',
            text: '', done: false, synthesis: data.synthesis, verdict: data.verdict,
          },
        }))
        break
      case 'agent_chunk':
        setCards((p) => {
          const c = p[data.agent_id]
          return c ? { ...p, [data.agent_id]: { ...c, text: c.text + data.chunk } } : p
        })
        break
      case 'agent_end':
        setCards((p) => ({
          ...p, [data.agent_id]: {
            ...p[data.agent_id], text: data.message || '', done: true,
          },
        }))
        break
      case 'user_turn':
        setUserTurn(true); setUserFinal(data.final || false)
        break
      case 'user_turn_timeout':
        setUserTurn(false)
        break
      case 'pause':
        setPaused(true)
        break
      case 'converge':
        setCards((p) => ({
          ...p, converge: {
            name: '聚类总结', color: '#d4a054', emoji: '📊',
            text: data.summary, done: true, isConverge: true,
          },
        }))
        break
      case 'question_suggestions':
        setSuggestions(data.suggestions)
        break
      case 'report':
        setReport(data.report); setStatus('讨论完成')
        break
      case 'done':
        setStatus('讨论完成')
        break
      case 'error':
        setStatus('错误：' + data.message)
        break
    }
  }, [])

  const handleUserSubmit = useCallback(async () => {
    const msg = userMsgRef.current?.value?.trim()
    if (!msg) return
    await fetch('/api/interject', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message: msg }),
    }).catch(() => {})
    userMsgRef.current.value = ''
    setUserTurn(false)
  }, [sessionId])

  const handleContinue = useCallback(async () => {
    await fetch(`/api/continue/${sessionId}`, { method: 'POST' }).catch(() => {})
    setPaused(false)
  }, [sessionId])

  const handleSkip = useCallback(async () => {
    setUserTurn(false)
    await fetch(`/api/continue/${sessionId}`, { method: 'POST' }).catch(() => {})
  }, [sessionId])

  const handleQuestionSuggest = useCallback(async () => {
    await fetch('/api/question-suggest', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    }).catch(() => {})
  }, [sessionId])

  const handleExport = useCallback(async () => {
    try {
      const resp = await fetch(`/api/export/${sessionId}`)
      const html = await resp.text()
      const blob = new Blob([html], { type: 'text/html' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `听涛阁-${topic.slice(0, 16)}.html`
      a.click(); URL.revokeObjectURL(url)
    } catch {}
  }, [sessionId, topic])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [cards, status])

  const isSynthesisPhase = phase.includes('正反合')
  const isVerdictPhase = phase.includes('判决')

  return (
    <>
      {/* ── Header ── */}
      <header className="shrink-0 border-b border-white/[0.04] bg-black/20">
        <div className="max-w-4xl mx-auto px-6 py-3 flex items-center justify-between">
          <button onClick={onBack}
            className="text-xs text-white/20 hover:text-white/50 transition-colors">
            ← 退出
          </button>
          <div className="text-center">
            <p className="text-sm text-white/50 truncate max-w-72">{topic}</p>
            <div className="flex items-center justify-center gap-2 mt-0.5">
              <span className="text-xs text-white/20">{status}</span>
              {round > 0 && (
                <span className="flex items-center gap-1.5">
                  <span className="text-[10px] text-white/10">·</span>
                  <span className="text-xs text-white/20">
                    {Array.from({ length: totalRounds || 3 }, (_, i) => (
                      <span key={i} className={i < round ? 'text-amber-400/60' : 'text-white/10'}>●</span>
                    ))}
                  </span>
                  <span className="text-[10px] text-white/10">·</span>
                  <span className="text-xs text-white/20">{phase}</span>
                </span>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            {suggestions === null && !report && (
              <button onClick={handleQuestionSuggest}
                className="text-xs px-2.5 py-1.5 rounded-lg border border-white/10 text-white/30 hover:text-white/60 hover:border-white/20 transition-all">
                💡 不会问？
              </button>
            )}
            {report && (
              <button onClick={handleExport}
                className="text-xs px-2.5 py-1.5 rounded-lg bg-amber-600/20 text-amber-300/70 hover:bg-amber-600/30 transition-all">
                📥 导出
              </button>
            )}
          </div>
        </div>

        {/* Agent tags */}
        {agents.length > 0 && (
          <div className="max-w-4xl mx-auto px-6 pb-3 flex flex-wrap gap-2">
            {agents.map((a) => (
              <span key={a.id}
                className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border"
                style={{ borderColor: a.color + '30', color: a.color, background: a.color + '08' }}>
                {a.emoji} {a.name}
              </span>
            ))}
          </div>
        )}
      </header>

      {/* ── Scrollable content ── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6 space-y-4">

          {/* Phase banner */}
          {phase && !isSynthesisPhase && !isVerdictPhase && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} key={phase}
              className="text-center py-3">
              <span className="text-[10px] text-white/15 tracking-[0.25em] uppercase">
                {phase}
              </span>
            </motion.div>
          )}

          {/* Synthesis / Verdict banner */}
          {(isSynthesisPhase || isVerdictPhase) && (
            <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
              className="text-center py-4 px-4 rounded-xl border mx-auto max-w-sm"
              style={{
                borderColor: isVerdictPhase ? 'rgba(212, 160, 84, 0.2)' : 'rgba(64, 184, 200, 0.15)',
                background: isVerdictPhase
                  ? 'linear-gradient(135deg, rgba(212,160,84,0.06), rgba(192,112,64,0.03))'
                  : 'linear-gradient(135deg, rgba(64,184,200,0.06), rgba(212,160,84,0.03))',
              }}>
              <span className="text-xs text-white/30 tracking-wider">
                {isVerdictPhase ? '⚖️ 最终判决' : '🤝 正反合——整合各方观点'}
              </span>
            </motion.div>
          )}

          {/* Cards */}
          <AnimatePresence mode="popLayout">
            {Object.entries(cards).map(([id, card], idx) => (
              <motion.div
                key={id}
                layout
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.35, delay: idx * 0.04 }}
                className="relative rounded-xl overflow-hidden border"
                style={{
                  borderColor: card.isConverge
                    ? 'rgba(212,160,84,0.15)'
                    : card.synthesis
                      ? 'rgba(64,184,200,0.15)'
                      : card.verdict
                        ? 'rgba(212,160,84,0.15)'
                        : card.done
                          ? 'rgba(232,224,208,0.06)'
                          : 'rgba(64,184,200,0.1)',
                  background: card.isConverge
                    ? 'linear-gradient(135deg, rgba(212,160,84,0.06), transparent)'
                    : card.synthesis
                      ? 'linear-gradient(135deg, rgba(64,184,200,0.05), rgba(212,160,84,0.02))'
                      : card.verdict
                        ? 'linear-gradient(135deg, rgba(212,160,84,0.06), rgba(192,112,64,0.02))'
                        : 'rgba(18,18,42,0.6)',
                }}>
                {/* Color bar */}
                <div className="absolute left-0 top-0 bottom-0 w-[3px] rounded-r-sm"
                  style={{
                    background: card.isConverge
                      ? 'linear-gradient(180deg, #d4a054, #c07040)'
                      : card.synthesis
                        ? 'linear-gradient(180deg, #40b8c8, #d4a054)'
                        : card.verdict
                          ? 'linear-gradient(180deg, #d4a054, #e8c074)'
                          : `linear-gradient(180deg, ${card.color}, ${card.color}88)`,
                  }} />

                <div className="pl-5 pr-5 py-4">
                  {/* Header */}
                  <div className="flex items-center gap-2.5 mb-2.5">
                    {card.isConverge ? (
                      <span className="text-base">📊</span>
                    ) : card.synthesis ? (
                      <span className="w-7 h-7 rounded-full bg-cyan-500/10 flex items-center justify-center text-xs">🤝</span>
                    ) : card.verdict ? (
                      <span className="w-7 h-7 rounded-full bg-amber-500/10 flex items-center justify-center text-xs">⚖️</span>
                    ) : (
                      <span className="text-lg">{card.emoji}</span>
                    )}
                    <span className="text-sm font-medium" style={{ color: card.color }}>
                      {card.name}
                    </span>
                    {card.synthesis && (
                      <span className="text-[10px] text-cyan-400/40 border border-cyan-400/20 px-1.5 rounded">正反合</span>
                    )}
                    {card.verdict && (
                      <span className="text-[10px] text-amber-400/40 border border-amber-400/20 px-1.5 rounded">判决</span>
                    )}
                    {!card.done && card.text && (
                      <span className="flex gap-0.5 ml-auto">
                        <span className="w-[3px] h-[3px] rounded-full bg-cyan-400 animate-pulse" />
                        <span className="w-[3px] h-[3px] rounded-full bg-cyan-400 animate-pulse [animation-delay:0.15s]" />
                        <span className="w-[3px] h-[3px] rounded-full bg-cyan-400 animate-pulse [animation-delay:0.3s]" />
                      </span>
                    )}
                  </div>

                  {/* Content */}
                  <div className="text-sm text-white/50 leading-[1.9] whitespace-pre-wrap min-h-[1.2em]">
                    {card.text || (
                      <span className="text-white/10 italic">{card.done ? '' : '思考中…'}</span>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Suggestions */}
          {suggestions && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="rounded-xl p-5 border border-cyan-500/10 bg-cyan-500/3">
              <h4 className="text-sm font-medium text-cyan-300/60 mb-3">💡 不知道怎么问？试试这些角度</h4>
              <div className="text-sm text-white/40 leading-relaxed whitespace-pre-wrap">{suggestions}</div>
            </motion.div>
          )}

          {/* Report */}
          {report && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              className="rounded-xl p-6 mt-8 border"
              style={{
                borderColor: 'rgba(212,160,84,0.15)',
                background: 'linear-gradient(135deg, rgba(212,160,84,0.06), rgba(64,184,200,0.03))',
              }}>
              <h3 className="text-base font-medium text-amber-300/60 mb-4">📝 各方观点速览</h3>
              <div className="text-sm text-white/50 leading-[1.9] whitespace-pre-wrap">{report}</div>
            </motion.div>
          )}
        </div>
      </div>

      {/* ── Pause bar ── */}
      {paused && (
        <div className="shrink-0 border-t border-white/[0.04] px-6 py-3 bg-black/20">
          <div className="max-w-3xl mx-auto flex items-center justify-center gap-4">
            <span className="text-sm text-white/20">看完这段了？</span>
            <button onClick={handleContinue}
              className="text-sm px-5 py-1.5 rounded-lg bg-amber-600/20 text-amber-300/70 hover:bg-amber-600/30 transition-all">
              继续 →
            </button>
          </div>
        </div>
      )}

      {/* ── User input ── */}
      {userTurn && (
        <div className="shrink-0 border-t border-white/[0.04] px-6 py-3 bg-black/30 backdrop-blur">
          <div className="max-w-3xl mx-auto flex gap-2">
            <input ref={userMsgRef} type="text" autoFocus
              placeholder="你的想法（回车发送，或等待自动继续）..."
              className="flex-1 bg-white/[0.04] border border-white/10 rounded-xl px-4 py-2 text-sm
                         text-white/70 placeholder-white/20 focus:outline-none focus:border-amber-500/30
                         transition-all"
              onKeyDown={(e) => e.key === 'Enter' && handleUserSubmit()} />
            <button onClick={handleUserSubmit}
              className="px-4 py-2 rounded-xl text-sm bg-amber-600/20 text-amber-300/70
                         hover:bg-amber-600/30 transition-all shrink-0">
              发送
            </button>
            <button onClick={handleSkip}
              className="px-3 py-2 rounded-xl text-xs border border-white/10 text-white/20
                         hover:text-white/40 transition-all shrink-0">
              跳过
            </button>
          </div>
        </div>
      )}
    </>
  )
}
