import React from 'react'

export function ActivePositions({ positions }) {
  const open = positions.filter(p => p.status === 'OPEN')

  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">ACTIVE POSITIONS</span>
        <span className="text-xs text-forge-muted">{open.length} open</span>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-hidden">
        {open.length === 0 ? (
          <div className="flex items-center justify-center h-full text-forge-muted text-xs">
            NO OPEN POSITIONS
          </div>
        ) : (
          <div className="divide-y divide-forge-border">
            {open.map(pos => {
              const pnl = pos.unrealized_pnl ?? 0
              const isUp = pnl >= 0
              return (
                <div key={pos.id} className="px-3 py-2 fade-in">
                  <div className="flex justify-between items-start">
                    <div className="flex-1 min-w-0 mr-2">
                      <div className="text-xs text-forge-text truncate">{pos.question}</div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={pos.direction === 'YES' ? 'tag-green' : 'tag-red'}>
                          {pos.direction}
                        </span>
                        <span className="text-xs text-forge-muted">${pos.size_usd?.toFixed(0)}</span>
                        <span className="text-xs text-forge-muted">@{pos.entry_price?.toFixed(3)}</span>
                      </div>
                    </div>
                    <div className={`text-sm font-semibold ${isUp ? 'text-forge-accent' : 'text-forge-red'}`}>
                      {isUp ? '+' : ''}{pnl.toFixed(2)}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
