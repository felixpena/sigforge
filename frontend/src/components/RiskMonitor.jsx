import React from 'react'

function Metric({ label, value, color, bar, barColor }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex justify-between items-center">
        <span className="text-xs text-forge-muted">{label}</span>
        <span className="text-xs font-bold" style={{ color: color || '#c0cce0' }}>{value}</span>
      </div>
      {bar !== undefined && (
        <div className="h-0.5 bg-forge-border rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${Math.min(100, Math.max(0, bar))}%`, background: barColor || '#00aaff' }}
          />
        </div>
      )}
    </div>
  )
}

export function RiskMonitor({ portfolio, riskOutput }) {
  const deployed = portfolio?.deployed ?? 0
  const bankroll = portfolio?.bankroll ?? 1000
  const drawdown = portfolio?.session_drawdown ?? 0
  const health = portfolio?.session_health ?? 'GREEN'

  const exposure = bankroll > 0 ? (deployed / bankroll) * 100 : 0
  const kelly = riskOutput?.kelly_fraction ? (riskOutput.kelly_fraction * 100).toFixed(1) : '--'
  const concentration = riskOutput?.portfolio_concentration_after
    ? (riskOutput.portfolio_concentration_after * 100).toFixed(1)
    : '--'
  const corrRisk = riskOutput?.correlation_risk ?? '--'
  const hedgeScore = Math.max(0, 100 - exposure)

  const healthColor = { GREEN: '#00ff88', YELLOW: '#ffcc00', RED: '#ff3366' }[health]
  const exposureColor = exposure > 60 ? '#ff3366' : exposure > 35 ? '#ffcc00' : '#00ff88'

  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">RISK MONITOR</span>
        <span className="text-xs font-bold" style={{ color: healthColor }}>{health}</span>
      </div>

      <div className="flex-1 p-3 flex flex-col gap-2.5">
        <Metric
          label="EXP — Exposure"
          value={`${exposure.toFixed(1)}%`}
          color={exposureColor}
          bar={exposure}
          barColor={exposureColor}
        />
        <Metric
          label="DPL — Deployed"
          value={`$${deployed.toFixed(0)}`}
          color="#00aaff"
          bar={(deployed / bankroll) * 100}
          barColor="#00aaff"
        />
        <Metric
          label="SHP — Session DD"
          value={`${drawdown.toFixed(1)}%`}
          color={drawdown > 15 ? '#ff3366' : drawdown > 8 ? '#ffcc00' : '#00ff88'}
          bar={drawdown * 5}
          barColor={drawdown > 15 ? '#ff3366' : '#ffcc00'}
        />
        <Metric
          label="HDG — Hedge Score"
          value={`${hedgeScore.toFixed(0)}`}
          color="#9945ff"
          bar={hedgeScore}
          barColor="#9945ff"
        />
        <Metric
          label="KLY — Kelly"
          value={kelly === '--' ? '--' : `${kelly}%`}
          color="#ffcc00"
        />
        <Metric
          label="CORR — Correlation"
          value={corrRisk}
          color={corrRisk === 'HIGH' ? '#ff3366' : corrRisk === 'MEDIUM' ? '#ffcc00' : '#00ff88'}
        />
      </div>
    </div>
  )
}
