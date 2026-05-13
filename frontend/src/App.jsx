import { useState, useCallback } from 'react'
import ModeSelector from './components/ModeSelector'
import Discussion from './components/Discussion'

const MODE_INFO = {
  debate: { name: '辩论', desc: '多角色交锋，帮你把问题想透', icon: '⚔️', cat: 'study' },
  brainstorm: { name: '头脑风暴', desc: '天马行空出主意，互相激发', icon: '🧠', cat: 'study' },
  socratic: { name: '苏格拉底追问', desc: '不断追问，逼你自己想通', icon: '❓', cat: 'study' },
  mock_defense: { name: '模拟答辩', desc: '模拟评委连环提问', icon: '🎤', cat: 'study' },
  critique: { name: '批评模式', desc: '写完后多角度挑刺', icon: '🔎', cat: 'study' },
  compare: { name: '观点对比', desc: '逐条对比，高亮分歧', icon: '⚖️', cat: 'study' },
  direction_explore: { name: '方向探索', desc: '从零开始找创新创业方向', icon: '🧭', cat: 'startup' },
  bp_polish: { name: 'BP 打磨', desc: '商业计划书逐章挑刺', icon: '📋', cat: 'startup' },
  roadshow: { name: '路演模拟', desc: '模拟投资人追问', icon: '🎯', cat: 'startup' },
  business_model: { name: '商业模式辩论', desc: '多个模式假设互相攻防', icon: '🏢', cat: 'startup' },
  risk_explore: { name: '风险勘探', desc: '全员找盲区', icon: '⚠️', cat: 'startup' },
  track_compare: { name: '赛道对比', desc: '两个方向谁更靠谱', icon: '🔄', cat: 'startup' },
  pain_find: { name: '痛点发掘', desc: '从方向到具体问题', icon: '🕳️', cat: 'startup' },
  contest_prep: { name: '比赛备战', desc: '互联网+等路演模拟', icon: '🏆', cat: 'startup' },
}

export default function App() {
  const [step, setStep] = useState('home')
  const [mode, setMode] = useState('')
  const [topic, setTopic] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [loading, setLoading] = useState(false)

  const handleModeSelect = useCallback((m) => {
    setMode(m)
    setStep('setup')
  }, [])

  const handleStart = useCallback(async () => {
    if (!topic.trim() && mode !== 'direction_explore') return
    setLoading(true)
    try {
      const body = { topic: topic.trim() || '方向探索', mode, rounds: 3 }
      const resp = await fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await resp.json()
      setSessionId(data.session_id)
      setStep('discuss')
    } catch (e) {
      alert('启动失败：' + e.message)
    } finally {
      setLoading(false)
    }
  }, [topic, mode])

  const handleBack = useCallback(() => {
    setStep('home')
    setMode('')
    setTopic('')
    setSessionId('')
  }, [])

  // ── Home screen ──
  if (step === 'home') {
    return (
      <div className="min-h-screen bg-ink-texture">
        <header className="border-b border-white/5 px-6 py-5">
          <div className="max-w-5xl mx-auto flex items-center gap-4">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500/30 to-cyan-500/20 border border-white/10 flex items-center justify-center text-sm">
              🏯
            </div>
            <div>
              <h1 className="text-lg font-heading tracking-wider text-white/90">
                听涛阁
              </h1>
              <p className="text-xs text-white/30 tracking-wide">
                你的反谄媚学习伙伴
              </p>
            </div>
          </div>
        </header>

        <main className="max-w-5xl mx-auto px-6 py-10">
          <div className="text-center mb-10 animate-fade-up">
            <h2 className="text-2xl font-heading text-white/80 tracking-wide mb-2">
              选择讨论模式
            </h2>
            <p className="text-sm text-white/30">
              选一个模式，开始你的思考之旅
            </p>
          </div>

          <ModeSelector
            modes={MODE_INFO}
            onSelect={handleModeSelect}
          />
        </main>
      </div>
    )
  }

  // ── Setup screen (topic input) ──
  if (step === 'setup') {
    const m = MODE_INFO[mode]
    return (
      <div className="min-h-screen bg-ink-texture flex flex-col">
        <header className="border-b border-white/5 px-6 py-3">
          <div className="max-w-3xl mx-auto flex items-center justify-between">
            <button onClick={handleBack} className="text-sm text-white/30 hover:text-white/60 transition-colors">
              ← 返回
            </button>
            <span className="text-xs text-white/20">{m?.icon} {m?.name}</span>
            <div className="w-12" />
          </div>
        </header>

        <main className="flex-1 flex items-center justify-center px-6">
          <div className="max-w-lg w-full animate-fade-up">
            <div className="text-center mb-6">
              <span className="text-3xl mb-3 block">{m?.icon}</span>
              <h2 className="text-xl font-heading text-white/80 mb-1">{m?.name}</h2>
              <p className="text-sm text-white/30">{m?.desc}</p>
            </div>

            {mode === 'direction_explore' ? (
              <div className="bg-card rounded-2xl p-8 text-center">
                <p className="text-sm text-white/40 mb-6">
                  还没有 idea？AI 帮你从势能扫描到方向收窄
                </p>
                <button
                  onClick={handleStart}
                  disabled={loading}
                  className="btn-gold px-8 py-3 rounded-xl text-sm"
                >
                  {loading ? '启动中...' : '开始探索 →'}
                </button>
              </div>
            ) : (
              <div className="bg-card rounded-2xl p-6 space-y-4">
                <textarea
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="粘贴作业题目、文章，或者描述你的问题…"
                  className="input-ink w-full rounded-xl p-4 text-sm h-28 resize-none"
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleStart}
                    disabled={loading || !topic.trim()}
                    className="btn-gold flex-1 py-2.5 rounded-xl text-sm"
                  >
                    {loading ? '启动中...' : '开始讨论 →'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    )
  }

  // ── Discussion screen ──
  return (
    <div className="min-h-screen bg-ink-texture flex flex-col">
      <Discussion
        sessionId={sessionId}
        mode={mode}
        topic={topic}
        onBack={handleBack}
      />
    </div>
  )
}
