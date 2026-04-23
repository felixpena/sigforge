import React from 'react'

const AGENTS = ['SCANNER', 'SIGNAL', 'RISK', 'EXECUTION']

const AGENT_COLORS = {
  SCANNER: '#00aaff',
  SIGNAL: '#9945ff',
  RISK: '#ffcc00',
  EXECUTION: '#00ff88',
}

export function AgentStatus({ connected, cycleCount, lastScan }) {
  const isActive = connected

  return (
    <div className="flex items-center gap-4">
      {/* Connection status */}
      <div className="flex items-center gap-1.5">
        <div className={`w-2 h-2 rounded-full ${isActive ? 'bg-forge-accent' : 'bg-forge-red'} ${isActive ? 'animate-pulse' : ''}`} />
        <span className={`text-xs font-semibold ${isActive ? 'text-forge-accent' : 'text-forge-red'}`}>
          {isActive ? 'LIVE' : 'OFFLINE'}
        </span>
      </div>

      {/* Agent indicators */}
      <div className="flex items-center gap-2">
        {AGENTS.map(agent => (
          <div key={agent} className="flex items-center gap-1">
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: isActive ? AGENT_COLORS[agent] : '#3a4055' }}
            />
            <span className="text-xs" style={{ color: isActive ? AGENT_COLORS[agent] : '#3a4055' }}>
              {agent.slice(0, 4)}
            </span>
          </div>
        ))}
      </div>

      {/* Cycle count */}
      {cycleCount > 0 && (
        <span className="text-xs text-forge-muted">CYC#{cycleCount}</span>
      )}

      {/* Last scan time */}
      {lastScan?.scan_timestamp && (
        <span className="text-xs text-forge-muted">
          {new Date(lastScan.scan_timestamp).toLocaleTimeString('en-US', { hour12: false })}
        </span>
      )}
    </div>
  )
}
