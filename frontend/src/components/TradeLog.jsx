import React from 'react'

function formatTime(ts) {
  if (!ts) return '--:--'
  try {
    return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return '--:--'
  }
}

export function TradeLog({ trades }) {
  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">TRADE LOG</span>
        <span className="text-xs text-forge-muted">{trades.length} fills</span>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-hidden">
        {trades.length === 0 ? (
          <div className="flex items-center justify-center h-full text-forge-muted text-xs">
            NO FILLS YET
          </div>
        ) : (
          <div className="divide-y divide-forge-border/50">
            {trades.map((trade, i) => (
              <div key={trade.id || i} className="px-3 py-2 fade-in">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <span className={trade.direction === 'YES' ? 'tag-green' : 'tag-red'}>
                      {trade.direction}
                    </span>
                    {trade.paper && (
                      <span className="text-xs text-forge-yellow bg-forge-yellow/10 px-1 rounded">PAPER</span>
                    )}
                    <span className="text-xs text-forge-text font-semibold">
                      ${trade.size_usd?.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-forge-muted">@{trade.price?.toFixed(3)}</span>
                    <span className={`text-xs ${
                      trade.status === 'FILLED' ? 'text-forge-accent' :
                      trade.status === 'CANCELLED' ? 'text-forge-red' :
                      'text-forge-yellow'
                    }`}>
                      {trade.status}
                    </span>
                  </div>
                </div>
                <div className="flex justify-between mt-0.5">
                  <div className="text-xs text-forge-muted truncate max-w-48">{trade.question || trade.market_id}</div>
                  <div className="text-xs text-forge-dim shrink-0 ml-2">{formatTime(trade.timestamp)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
