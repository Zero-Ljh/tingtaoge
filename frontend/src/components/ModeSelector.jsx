const CATEGORIES = [
  {
    label: '通用学习',
    key: 'study',
    keys: ['debate', 'brainstorm', 'socratic', 'mock_defense', 'critique', 'compare'],
  },
  {
    label: '创新创业',
    key: 'startup',
    keys: ['direction_explore', 'bp_polish', 'roadshow', 'business_model', 'risk_explore', 'track_compare', 'pain_find', 'contest_prep'],
  },
]

export default function ModeSelector({ modes, onSelect }) {
  return (
    <div className="space-y-8">
      {CATEGORIES.map((cat, ci) => (
        <div key={cat.key} className="animate-fade-up" style={{ animationDelay: `${ci * 0.1}s` }}>
          <h3 className="text-xs font-medium text-white/20 uppercase tracking-[0.15em] mb-4 ml-1">
            {cat.label}
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {cat.keys.map((key, ki) => {
              const m = modes[key]
              if (!m) return null
              return (
                <button
                  key={key}
                  onClick={() => onSelect(key)}
                  className="mode-card bg-card rounded-xl p-4 text-left group"
                  style={{ animationDelay: `${(ci * 6 + ki) * 0.05}s` }}
                >
                  <div className="text-xl mb-2 group-hover:scale-110 transition-transform duration-300">
                    {m.icon}
                  </div>
                  <div className="text-sm font-medium text-white/70 group-hover:text-white/90 transition-colors">
                    {m.name}
                  </div>
                  <div className="text-xs text-white/20 mt-1 line-clamp-1 group-hover:text-white/30 transition-colors">
                    {m.desc}
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
