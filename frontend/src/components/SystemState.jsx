import React from 'react'

function Gauge({ label, value, unit, color, max = 100 }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div className="flex flex-col items-center">
      <div className="relative w-12 h-12">
        <svg viewBox="0 0 40 40" className="w-full h-full -rotate-90">
          <circle cx="20" cy="20" r="16" fill="none" stroke="#1a1f2e" strokeWidth="3" />
          <circle
            cx="20" cy="20" r="16" fill="none"
            stroke={color}
            strokeWidth="3"
            strokeDasharray={`${pct} 100`}
            strokeLinecap="round"
            style={{ filter: pct > 70 ? `drop-shadow(0 0 3px ${color})` : 'none' }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center rotate-90">
          <span className="text-xs font-bold" style={{ color, fontSize: '9px' }}>
            {typeof value === 'number' ? value.toFixed(0) : value}
          </span>
        </div>
      </div>
      <span className="text-xs text-forge-muted mt-0.5">{label}</span>
    </div>
  )
}

export function SystemState({ marketState, opportunities }) {
  const count = opportunities.length
  const avgSpread = count > 0
    ? opportunities.reduce((s, o) => s + (o.current_price > 0 ? Math.abs(0.5 - o.current_price) * 200 : 0), 0) / count
    : 0
  const volScore = Math.min(100, (marketState?.total_volume_session ?? 0) / 1000)
  const bias = marketState?.session_bias ?? 'NEUTRAL'

  const biasColor = { RISK_ON: '#00ff88', RISK_OFF: '#ff3366', NEUTRAL: '#ffcc00' }[bias] ?? '#ffcc00'
  const biasNum = { RISK_ON: 75, RISK_OFF: 25, NEUTRAL: 50 }[bias] ?? 50

  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">SYSTEM STATE</span>
        <span className="text-xs font-bold" style={{ color: biasColor }}>{bias}</span>
      </div>

      <div className="flex-1 flex items-center justify-around p-3">
        <Gauge label="VOL" value={volScore} color="#00aaff" max={100} />
        <Gauge label="SPREAD" value={avgSpread} color="#9945ff" max={50} />
        <Gauge label="FLOW" value={Math.min(100, count * 8)} color="#00ff88" max={100} />
        <Gauge label="BIAS" value={biasNum} color={biasColor} max={100} />
      </div>
    </div>
  )
}
