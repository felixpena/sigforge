import React from 'react'

export function LivePnL({ portfolio }) {
  const pnl = portfolio?.session_pnl ?? 0
  const isPositive = pnl >= 0
  const bankroll = portfolio?.bankroll ?? 1000
  const pnlPct = bankroll > 0 ? (pnl / bankroll) * 100 : 0
  const health = portfolio?.session_health ?? 'GREEN'

  const healthColor = {
    GREEN: 'text-forge-accent',
    YELLOW: 'text-forge-yellow',
    RED: 'text-forge-red',
  }[health]

  return (
    <div className="panel flex flex-col items-center justify-center py-4 px-6 relative">
      <div className="panel-header absolute top-0 left-0 right-0">
        <span className="panel-title">LIVE P&L</span>
        <span className={`text-xs font-bold ${healthColor}`}>{health}</span>
      </div>

      <div className="mt-6">
        <div className={`text-5xl font-bold tracking-tight ${isPositive ? 'text-forge-accent neon-green' : 'text-forge-red neon-red'}`}>
          {isPositive ? '+' : ''}{pnl.toFixed(2)}
          <span className="text-2xl ml-1">$</span>
        </div>
        <div className={`text-center text-sm mt-1 ${isPositive ? 'text-forge-accent/70' : 'text-forge-red/70'}`}>
          {isPositive ? '▲' : '▼'} {Math.abs(pnlPct).toFixed(2)}% session
        </div>
      </div>

      <div className="flex gap-6 mt-4 text-xs text-forge-muted">
        <div className="text-center">
          <div className="text-forge-text font-semibold">${(portfolio?.deployed ?? 0).toFixed(0)}</div>
          <div>deployed</div>
        </div>
        <div className="text-center">
          <div className="text-forge-text font-semibold">${(portfolio?.available ?? bankroll).toFixed(0)}</div>
          <div>available</div>
        </div>
        <div className="text-center">
          <div className="text-forge-text font-semibold">{portfolio?.open_positions ?? 0}</div>
          <div>positions</div>
        </div>
      </div>

      {portfolio?.session_drawdown > 0 && (
        <div className="mt-2 text-xs text-forge-yellow">
          DD: {portfolio.session_drawdown.toFixed(1)}%
        </div>
      )}
    </div>
  )
}
