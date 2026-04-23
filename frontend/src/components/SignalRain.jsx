import React, { useEffect, useRef } from 'react'

const PRIORITY_COLORS = {
  HIGH: '#00ff88',
  MEDIUM: '#ffcc00',
  LOW: '#00aaff',
}

const ANOMALY_LABELS = {
  price_drift: 'DRIFT',
  volume_spike: 'VOL↑',
  liquidity_gap: 'LIQ∅',
  correlation_divergence: 'CORR',
}

export function SignalRain({ opportunities }) {
  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">SIGNAL RAIN</span>
        <span className="text-xs text-forge-muted">{opportunities.length} signals</span>
      </div>

      <div className="flex-1 overflow-hidden relative">
        {opportunities.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="text-forge-muted text-xs mb-2">SCANNING MARKETS</div>
              <div className="flex gap-1 justify-center">
                {[...Array(5)].map((_, i) => (
                  <div
                    key={i}
                    className="w-0.5 bg-forge-accent/30 rounded-full"
                    style={{
                      height: `${20 + Math.random() * 30}px`,
                      animation: `pulse ${1 + i * 0.2}s ease-in-out infinite alternate`,
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="p-2 space-y-1 overflow-y-auto h-full scrollbar-hidden">
            {opportunities.slice(0, 20).map((opp, i) => {
              const color = PRIORITY_COLORS[opp.priority] || '#5a6580'
              const label = ANOMALY_LABELS[opp.anomaly_type] || opp.anomaly_type
              const score = opp.anomaly_score ?? 0

              return (
                <div
                  key={opp.market_id || i}
                  className="flex items-center gap-2 px-2 py-1.5 rounded fade-in"
                  style={{ borderLeft: `2px solid ${color}20`, background: `${color}08` }}
                >
                  {/* Score bar */}
                  <div className="shrink-0 w-8">
                    <div className="text-xs font-bold" style={{ color }}>
                      {Math.round(score)}
                    </div>
                  </div>

                  {/* Anomaly type */}
                  <div
                    className="shrink-0 text-xs font-semibold px-1 rounded"
                    style={{ color, background: `${color}20` }}
                  >
                    {label}
                  </div>

                  {/* Price */}
                  <div className="shrink-0 text-xs text-forge-muted w-12">
                    {(opp.current_price * 100).toFixed(1)}¢
                  </div>

                  {/* Question */}
                  <div className="flex-1 text-xs text-forge-text truncate">
                    {opp.question}
                  </div>

                  {/* Priority */}
                  <div
                    className="shrink-0 text-xs font-bold"
                    style={{ color }}
                  >
                    {opp.priority}
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
