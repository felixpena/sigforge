import React from 'react'

const BANDS = [
  { key: 'ALPHA', label: 'ALPHA', color: '#00ff88', desc: 'Trend momentum' },
  { key: 'GAMMA', label: 'GAMMA', color: '#9945ff', desc: 'Vol sensitivity' },
  { key: 'THETA', label: 'THETA', color: '#ffcc00', desc: 'Time decay' },
  { key: 'FLOW', label: 'FLOW', color: '#00aaff', desc: 'Order flow' },
]

function computeBandValues(opportunities, portfolio) {
  const count = opportunities.length
  const avgScore = count > 0
    ? opportunities.reduce((s, o) => s + (o.anomaly_score ?? 0), 0) / count
    : 0
  const highCount = opportunities.filter(o => o.priority === 'HIGH').length
  const volSpikes = opportunities.filter(o => o.anomaly_type === 'volume_spike').length
  const sessionPnl = portfolio?.session_pnl ?? 0
  const drawdown = portfolio?.session_drawdown ?? 0

  return {
    ALPHA: Math.min(100, avgScore * 1.1),
    GAMMA: Math.min(100, (highCount / Math.max(count, 1)) * 100 * 1.5),
    THETA: Math.min(100, Math.max(0, 100 - drawdown * 3)),
    FLOW: Math.min(100, (volSpikes / Math.max(count, 1)) * 100 * 2 + 20),
  }
}

export function SignalBands({ opportunities, portfolio }) {
  const values = computeBandValues(opportunities, portfolio)

  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">SIGNAL BANDS</span>
      </div>

      <div className="flex-1 p-3 flex flex-col justify-around">
        {BANDS.map(band => {
          const val = values[band.key] ?? 0
          return (
            <div key={band.key}>
              <div className="flex justify-between items-center mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold w-12" style={{ color: band.color }}>{band.label}</span>
                  <span className="text-xs text-forge-muted">{band.desc}</span>
                </div>
                <span className="text-xs font-semibold" style={{ color: band.color }}>
                  {val.toFixed(0)}
                </span>
              </div>
              <div className="h-1 bg-forge-border rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${val}%`,
                    background: `linear-gradient(90deg, ${band.color}80, ${band.color})`,
                    boxShadow: val > 70 ? `0 0 6px ${band.color}60` : 'none',
                  }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
