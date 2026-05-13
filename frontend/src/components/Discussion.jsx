import { useState, useEffect, useRef, useCallback } from 'react'

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

  // SSE connection
  useEffect(() => {
    if (!sessionId) return
    const evtSource = new EventSource(`/api/stream/${sessionId}`)
    setAgents([]); setCards({}); setReport(null)
    setUserTurn(false); setPaused(false); setSuggestions(null); setRound(0)

    evtSource.onmessage = (event) => {
      try { handleEvent(JSON.parse(event.data)) } catch {}
    }
    evtSource.onerror = () => { setStatus('连接断开'); evtSource.close() }
    return () => evtSource.close()
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
          ...p,
          [data.agent_id]: {
            name: data.agent_name, color: data.color,
            emoji: data.emoji || '', text: '', done: false,
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
          ...p,
          [data.agent_id]: {
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
          ...p,
          converge: { name: '聚类总结', color: '#d4a054', emoji: '📊', text: data.summary, done: true, isConverge: true },
        }))
        break
      case 'question_suggestions':
        setSuggestions(data.suggestions)
        break
      case 'report':
        setReport(data.report)
        setStatus('讨论完成')
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
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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

  // Auto scroll
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [cards, status])

  const cardEntries = Object.entries(cards)
  const isExploring = mode === 'direction_explore'

  return (
    <>
      {/* Header */}
      <header className="border-b border-white/5 px-6 py-3 shrink-0">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <button
            onClick={onBack}
            className="text-xs text-white/20 hover:text-white/50 transition-colors"
          >
            ← 退出
          </button>
          <div className="text-center">
            <p className="text-sm text-white/60 truncate max-w-80">{topic}</p>
            <p className="text-xs text-white/20 mt-0.5">
              {status}
              {round > 0 && ` · ${round}/${totalRounds} 轮`}
              {phase && ` · ${phase}`}
            </p>
          </div>
          <div className="flex gap-2">
            {suggestions === null && !report && (
              <button onClick={handleQuestionSuggest}
                className="btn-ghost text-xs px-3 py-1.5 rounded-lg">
                💡 不会问？
              </button>
            )}
            {report && (
              <button onClick={handleExport}
                className="btn-gold text-xs px-3 py-1.5 rounded-lg">
                📥 导出
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Scrollable cards area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-4xl mx-auto space-y-4">

          {/* Agent list + cards */}
          {agents.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-4 animate-fade-up">
              {agents.map((a) => (
                <span
                  key={a.id}
                  className="text-xs px-2.5 py-1 rounded-full border"
                  style={{
                    borderColor: a.color + '30',
                    color: a.color,
                    background: a.color + '08',
                  }}
                >
                  {a.emoji} {a.name}
                </span>
              ))}
            </div>
          )}

          {/* Round indicator */}
          {round > 0 && (
            <div className="text-center py-3">
              <span className="text-xs text-white/15 tracking-[0.2em] uppercase">
                第 {round}/{totalRounds} 轮{' · '}
                {phase || (isExploring ? '方向探索' : '讨论')}
              </span>
            </div>
          )}

          {/* Role cards */}
          {cardEntries.map(([id, card], idx) => (
            <div
              key={id}
              className="role-card bg-card rounded-2xl overflow-hidden"
              style={{
                animation: `fadeSlideUp 0.4s ease-out ${idx * 0.08}s both`,
                borderColor: card.isConverge
                  ? 'rgba(212, 160, 84, 0.2)'
                  : card.done
                    ? 'rgba(232, 224, 208, 0.08)'
                    : 'rgba(64, 184, 200, 0.15)',
              }}
            >
              <div
                className="card-accent"
                style={{
                  background: card.isConverge
                    ? 'linear-gradient(180deg, #d4a054, #c07040)'
                    : `linear-gradient(180deg, ${card.color}, ${card.color}88)`,
                }}
              />
              <div className="pl-5 pr-5 py-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">{card.emoji}</span>
                  <span className="text-sm font-medium" style={{ color: card.color }}>
                    {card.name}
                  </span>
                  {!card.done && card.text && (
                    <span className="flex gap-1 ml-1">
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                    </span>
                  )}
                </div>
                <div className="text-sm text-white/60 leading-[1.8] whitespace-pre-wrap min-h-[1.5em]">
                  {card.text || (
                    <span className="text-white/15 italic">
                      {card.done ? '' : '思考中…'}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* Suggestions */}
          {suggestions && (
            <div className="bg-card rounded-2xl p-5 border border-cyan-500/10 animate-fade-up">
              <h4 className="text-sm font-medium text-cyan-300/80 mb-3">💡 不知道怎么问？试试这些角度</h4>
              <div className="text-sm text-white/50 leading-relaxed whitespace-pre-wrap">{suggestions}</div>
            </div>
          )}

          {/* Report */}
          {report && (
            <div className="summary-card rounded-2xl p-6 mt-8 animate-fade-up">
              <h3 className="text-base font-heading text-amber-300/80 mb-4">
                📝 各方观点速览
              </h3>
              <div className="text-sm text-white/60 leading-[1.9] whitespace-pre-wrap">
                {report}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Pause bar */}
      {paused && (
        <div className="border-t border-white/5 px-6 py-3 shrink-0">
          <div className="max-w-4xl mx-auto flex items-center justify-center gap-4">
            <p className="text-sm text-white/30">看完这段了吗？</p>
            <button onClick={handleContinue}
              className="btn-gold text-sm px-5 py-1.5 rounded-lg">
              继续 →
            </button>
          </div>
        </div>
      )}

      {/* User input bar */}
      {userTurn && (
        <div className="border-t border-white/5 px-6 py-3 shrink-0">
          <div className="max-w-4xl mx-auto flex gap-2">
            <input
              ref={userMsgRef}
              type="text"
              placeholder="你的想法（回车发送，或等 60 秒自动继续）..."
              className="input-ink flex-1 rounded-xl px-4 py-2 text-sm"
              onKeyDown={(e) => e.key === 'Enter' && handleUserSubmit()}
              autoFocus
            />
            <button onClick={handleUserSubmit}
              className="btn-gold px-4 py-2 rounded-xl text-sm">
              发送
            </button>
            <button onClick={handleSkip}
              className="btn-ghost px-3 py-2 rounded-xl text-xs">
              跳过
            </button>
          </div>
        </div>
      )}
    </>
  )
}
