import React, { useState, useCallback, useRef } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { LivePnL } from './components/LivePnL'
import { ActivePositions } from './components/ActivePositions'
import { ScanLog } from './components/ScanLog'
import { PnLChart } from './components/PnLChart'
import { SignalRain } from './components/SignalRain'
import { MarketScanner } from './components/MarketScanner'
import { TradeLog } from './components/TradeLog'
import { Performance } from './components/Performance'
import { SignalBands } from './components/SignalBands'
import { SystemState } from './components/SystemState'
import { RiskMonitor } from './components/RiskMonitor'
import { AgentStatus } from './components/AgentStatus'

const MAX_LOG_ENTRIES = 200
const MAX_PNL_HISTORY = 300

export default function App() {
  const [portfolio, setPortfolio] = useState(null)
  const [positions, setPositions] = useState([])
  const [trades, setTrades] = useState([])
  const [logEntries, setLogEntries] = useState([])
  const [pnlHistory, setPnlHistory] = useState([])
  const [opportunities, setOpportunities] = useState([])
  const [marketsScanned, setMarketsScanned] = useState(0)
  const [marketState, setMarketState] = useState(null)
  const [lastScan, setLastScan] = useState(null)
  const [lastRisk, setLastRisk] = useState(null)
  const [cycleCount, setCycleCount] = useState(0)
  const [paperMode, setPaperMode] = useState(true)

  const handleMessage = useCallback((msg) => {
    const { type, payload, timestamp } = msg

    switch (type) {
      case 'portfolio':
        setPortfolio(payload)
        break

      case 'positions':
        setPositions(payload.positions ?? [])
        break

      case 'log':
        setLogEntries(prev => {
          const next = [payload, ...prev]
          return next.slice(0, MAX_LOG_ENTRIES)
        })
        break

      case 'log_history':
        setLogEntries(payload.entries ?? [])
        break

      case 'trade_history':
        setTrades(payload.trades ?? [])
        break

      case 'pnl_history':
        setPnlHistory(payload.history ?? [])
        break

      case 'scan_complete':
        setMarketsScanned(payload.markets_scanned ?? 0)
        if (payload.market_state) setMarketState(payload.market_state)
        if (payload.opportunities) {
          setOpportunities(payload.opportunities)
        }
        setLastScan(payload)
        setCycleCount(c => c + 1)
        break

      case 'opportunity':
        setOpportunities(prev => {
          const exists = prev.find(o => o.market_id === payload.market_id)
          if (exists) return prev.map(o => o.market_id === payload.market_id ? payload : o)
          return [payload, ...prev].slice(0, 50)
        })
        break

      case 'risk':
        setLastRisk(payload)
        break

      case 'execution':
        if (payload.action === 'ENTER') {
          // Add to positions optimistically
          setPositions(prev => [...prev])
        }
        break

      case 'signal':
        // Log signal in scan log as well
        break

      case 'cycle_start':
        setCycleCount(payload.cycle ?? 0)
        break

      case 'system_status':
        setPaperMode(payload.paper_trading)
        break

      default:
        break
    }

    // Add pnl snapshot from portfolio updates
    if (type === 'portfolio' && payload.session_pnl !== undefined) {
      setPnlHistory(prev => {
        const snapshot = { timestamp: timestamp || new Date().toISOString(), pnl: payload.session_pnl }
        const next = [...prev, snapshot]
        return next.slice(-MAX_PNL_HISTORY)
      })
    }
  }, [])

  const { connected, reconnecting } = useWebSocket(handleMessage)

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col bg-forge-bg" style={{ maxHeight: '100vh' }}>

      {/* ── Reconnecting Overlay ─────────────────────────────────────── */}
      {reconnecting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none">
          <div className="bg-forge-panel border border-forge-yellow/40 rounded px-6 py-3 flex items-center gap-3 shadow-lg">
            <div className="w-2 h-2 rounded-full bg-forge-yellow animate-pulse" />
            <span className="text-sm font-bold text-forge-yellow tracking-widest">RECONNECTING...</span>
          </div>
        </div>
      )}

      {/* ── Top Bar ─────────────────────────────────────────────────────── */}
      <header className="h-9 shrink-0 border-b border-forge-border flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <span className="text-sm font-bold text-forge-accent tracking-widest">SIG//FORGE</span>
          {paperMode && (
            <span className="text-xs px-2 py-0.5 bg-forge-yellow/10 text-forge-yellow border border-forge-yellow/30 rounded">
              PAPER
            </span>
          )}
        </div>

        <AgentStatus
          connected={connected}
          cycleCount={cycleCount}
          lastScan={lastScan}
        />

        <div className="text-xs text-forge-muted">
          {new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
        </div>
      </header>

      {/* ── Main Grid ────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-hidden grid gap-px bg-forge-border" style={{
        gridTemplateColumns: '280px 1fr 1fr 260px',
        gridTemplateRows: '200px 1fr 180px',
      }}>

        {/* Row 1 */}

        {/* [0,0] Active Positions */}
        <div className="bg-forge-bg overflow-hidden">
          <ActivePositions positions={positions} />
        </div>

        {/* [0,1] Live P&L — spans 2 cols */}
        <div className="bg-forge-bg overflow-hidden col-span-2">
          <LivePnL portfolio={portfolio} />
        </div>

        {/* [0,3] Scan Log */}
        <div className="bg-forge-bg overflow-hidden">
          <ScanLog entries={logEntries} />
        </div>

        {/* Row 2 */}

        {/* [1,0] Signal Rain */}
        <div className="bg-forge-bg overflow-hidden">
          <SignalRain opportunities={opportunities} />
        </div>

        {/* [1,1] P&L Chart — spans 2 cols */}
        <div className="bg-forge-bg overflow-hidden col-span-2">
          <PnLChart history={pnlHistory} />
        </div>

        {/* [1,3] Right column — Signal Bands + System State + Risk */}
        <div className="bg-forge-bg overflow-hidden flex flex-col gap-px">
          <div className="flex-1 bg-forge-bg overflow-hidden">
            <SignalBands opportunities={opportunities} portfolio={portfolio} />
          </div>
        </div>

        {/* Row 3 */}

        {/* [2,0] Performance */}
        <div className="bg-forge-bg overflow-hidden">
          <Performance portfolio={portfolio} />
        </div>

        {/* [2,1] Market Scanner — spans 2 cols */}
        <div className="bg-forge-bg overflow-hidden col-span-2">
          <MarketScanner opportunities={opportunities} marketsScanned={marketsScanned} />
        </div>

        {/* [2,3] Risk Monitor */}
        <div className="bg-forge-bg overflow-hidden flex flex-col gap-px">
          <div className="h-1/2 bg-forge-bg overflow-hidden">
            <SystemState marketState={marketState} opportunities={opportunities} />
          </div>
          <div className="h-1/2 bg-forge-bg overflow-hidden">
            <RiskMonitor portfolio={portfolio} riskOutput={lastRisk} />
          </div>
        </div>

      </div>

      {/* ── Trade Log Bar ─────────────────────────────────────────────────── */}
      <div className="h-28 shrink-0 border-t border-forge-border bg-forge-bg">
        <TradeLog trades={trades} />
      </div>

    </div>
  )
}
