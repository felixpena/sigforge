import React from 'react'

const PRIORITY_DOT = {
  HIGH: 'bg-forge-accent',
  MEDIUM: 'bg-forge-yellow',
  LOW: 'bg-forge-blue',
}

export function MarketScanner({ opportunities, marketsScanned }) {
  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">MARKET SCANNER</span>
        <div className="flex items-center gap-3">
          {marketsScanned > 0 && (
            <span className="text-xs text-forge-muted">{marketsScanned} scanned</span>
          )}
          <span className="text-xs text-forge-muted">{opportunities.length} flagged</span>
        </div>
      </div>

      <div className="flex-1 overflow-x-auto overflow-y-auto scrollbar-hidden">
        {opportunities.length === 0 ? (
          <div className="flex items-center justify-center h-20 text-forge-muted text-xs">
            NO OPPORTUNITIES DETECTED
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-forge-border">
                <th className="text-left px-3 py-1.5 text-forge-muted font-normal">PRI</th>
                <th className="text-left px-3 py-1.5 text-forge-muted font-normal">QUESTION</th>
                <th className="text-right px-3 py-1.5 text-forge-muted font-normal">PRICE</th>
                <th className="text-right px-3 py-1.5 text-forge-muted font-normal">VOL 24H</th>
                <th className="text-right px-3 py-1.5 text-forge-muted font-normal">LIQ</th>
                <th className="text-right px-3 py-1.5 text-forge-muted font-normal">SCORE</th>
                <th className="text-left px-3 py-1.5 text-forge-muted font-normal">TYPE</th>
                <th className="text-right px-3 py-1.5 text-forge-muted font-normal">RESOLVES</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-forge-border/50">
              {opportunities.map((opp, i) => (
                <tr key={opp.market_id || i} className="hover:bg-forge-border/20 transition-colors fade-in">
                  <td className="px-3 py-1.5">
                    <div className="flex items-center gap-1.5">
                      <div className={`w-1.5 h-1.5 rounded-full ${PRIORITY_DOT[opp.priority] || 'bg-forge-muted'}`} />
                      <span className="text-forge-muted">{opp.priority?.charAt(0)}</span>
                    </div>
                  </td>
                  <td className="px-3 py-1.5">
                    <div className="max-w-xs truncate text-forge-text">{opp.question}</div>
                    <div className="text-forge-muted text-xs mt-0.5 truncate">{opp.reason}</div>
                  </td>
                  <td className="px-3 py-1.5 text-right font-semibold">
                    <span className={opp.current_price > 0.5 ? 'text-forge-accent' : 'text-forge-red'}>
                      {(opp.current_price * 100).toFixed(1)}¢
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-right text-forge-muted">
                    ${formatNum(opp.volume_24h)}
                  </td>
                  <td className="px-3 py-1.5 text-right text-forge-muted">
                    ${formatNum(opp.liquidity)}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <ScoreBar score={opp.anomaly_score} />
                  </td>
                  <td className="px-3 py-1.5">
                    <span className="tag-blue">{opp.anomaly_type?.replace('_', ' ')}</span>
                  </td>
                  <td className="px-3 py-1.5 text-right text-forge-muted">
                    {opp.time_to_resolution}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function ScoreBar({ score }) {
  const pct = Math.min(100, Math.max(0, score ?? 0))
  const color = pct >= 85 ? '#00ff88' : pct >= 70 ? '#ffcc00' : '#00aaff'
  return (
    <div className="flex items-center gap-1.5 justify-end">
      <div className="w-16 h-1 bg-forge-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span style={{ color }} className="w-7 text-right">{Math.round(pct)}</span>
    </div>
  )
}

function formatNum(n) {
  if (!n) return '0'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toFixed(0)
}
