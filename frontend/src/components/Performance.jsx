import React from 'react'
import { RadialBarChart, RadialBar, ResponsiveContainer } from 'recharts'

export function Performance({ portfolio }) {
  const winRate = portfolio?.win_rate ?? 0
  const avgProfit = portfolio?.avg_profit ?? 0
  const totalTrades = portfolio?.total_trades ?? 0
  const totalPnl = portfolio?.total_pnl ?? 0

  const metrics = [
    { label: 'WIN RATE', value: `${winRate.toFixed(1)}%`, color: winRate >= 60 ? '#00ff88' : winRate >= 40 ? '#ffcc00' : '#ff3366' },
    { label: 'AVG PROFIT', value: `$${avgProfit.toFixed(2)}`, color: avgProfit >= 0 ? '#00ff88' : '#ff3366' },
    { label: 'TOTAL TRADES', value: totalTrades.toString(), color: '#00aaff' },
    { label: 'TOTAL P&L', value: `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`, color: totalPnl >= 0 ? '#00ff88' : '#ff3366' },
  ]

  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">PERFORMANCE</span>
      </div>

      <div className="flex-1 p-3 flex flex-col gap-2">
        {metrics.map(m => (
          <div key={m.label} className="flex justify-between items-center">
            <span className="text-xs text-forge-muted">{m.label}</span>
            <span className="text-sm font-bold" style={{ color: m.color }}>{m.value}</span>
          </div>
        ))}

        {/* Win rate bar */}
        <div className="mt-2">
          <div className="flex justify-between text-xs text-forge-muted mb-1">
            <span>WIN</span>
            <span>LOSS</span>
          </div>
          <div className="h-1.5 bg-forge-border rounded-full overflow-hidden">
            <div
              className="h-full bg-forge-accent rounded-full transition-all duration-500"
              style={{ width: `${winRate}%` }}
            />
          </div>
        </div>

        {/* Trade counts */}
        <div className="flex justify-between text-xs mt-1">
          <span className="text-forge-accent">{portfolio?.winning_trades ?? 0}W</span>
          <span className="text-forge-red">{(totalTrades - (portfolio?.winning_trades ?? 0))}L</span>
        </div>
      </div>
    </div>
  )
}
