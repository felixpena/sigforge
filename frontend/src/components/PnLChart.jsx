import React from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

function formatTime(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const val = payload[0].value
  return (
    <div className="bg-forge-panel border border-forge-border rounded px-2 py-1 text-xs">
      <span className={val >= 0 ? 'text-forge-accent' : 'text-forge-red'}>
        {val >= 0 ? '+' : ''}{val?.toFixed(2)}$
      </span>
    </div>
  )
}

export function PnLChart({ history }) {
  const data = history.map(h => ({
    time: formatTime(h.timestamp),
    pnl: parseFloat(h.pnl?.toFixed(2) ?? 0),
  }))

  const minPnl = Math.min(...data.map(d => d.pnl), 0)
  const maxPnl = Math.max(...data.map(d => d.pnl), 0)
  const latest = data[data.length - 1]?.pnl ?? 0
  const isPositive = latest >= 0

  return (
    <div className="panel flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">SESSION P&L</span>
        <span className={`text-sm font-bold ${isPositive ? 'text-forge-accent' : 'text-forge-red'}`}>
          {isPositive ? '+' : ''}{latest.toFixed(2)}$
        </span>
      </div>

      <div className="flex-1 px-2 py-2">
        {data.length < 2 ? (
          <div className="flex items-center justify-center h-full text-forge-muted text-xs">
            COLLECTING DATA...
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <XAxis
                dataKey="time"
                tick={{ fontSize: 9, fill: '#5a6580', fontFamily: 'monospace' }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 9, fill: '#5a6580', fontFamily: 'monospace' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `${v > 0 ? '+' : ''}${v}`}
                domain={[Math.min(minPnl * 1.1, -1), Math.max(maxPnl * 1.1, 1)]}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#1a1f2e" strokeDasharray="3 3" />
              <Line
                type="monotone"
                dataKey="pnl"
                stroke={isPositive ? '#00ff88' : '#ff3366'}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
