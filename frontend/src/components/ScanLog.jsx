import React, { useRef, useEffect } from 'react'

const LEVEL_STYLES = {
  INFO: 'text-forge-muted',
  WARN: 'text-forge-yellow',
  ERROR: 'text-forge-red',
  TRADE: 'text-forge-accent font-semibold',
  VETO: 'text-forge-red font-semibold',
}

const AGENT_COLORS = {
  SCANNER: 'text-forge-blue',
  SIGNAL: 'text-forge-purple',
  RISK: 'text-forge-yellow',
  EXECUTION: 'text-forge-accent',
  SYSTEM: 'text-forge-muted',
}

function formatTime(ts) {
  if (!ts) return '--:--:--'
  try {
    return new Date(ts).toLocaleTimeString('en-US', { hour12: false })
  } catch {
    return '--:--:--'
  }
}

export function ScanLog({ entries }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [entries])

  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">SCAN LOG</span>
        <span className="text-xs text-forge-accent blink">● LIVE</span>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-hidden px-2 py-1 font-mono text-xs">
        {entries.length === 0 ? (
          <div className="text-forge-muted text-center py-4">AWAITING SIGNAL...</div>
        ) : (
          entries.map((entry, i) => (
            <div key={entry.id || i} className="flex gap-2 py-0.5 fade-in leading-relaxed">
              <span className="text-forge-dim shrink-0">{formatTime(entry.timestamp)}</span>
              <span className={`shrink-0 w-16 ${AGENT_COLORS[entry.agent] || 'text-forge-muted'}`}>
                {entry.agent}
              </span>
              <span className={LEVEL_STYLES[entry.level] || 'text-forge-text'}>
                {entry.message}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
