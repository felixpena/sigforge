"""
SIG//FORGE Orchestrator
Runs all 4 agents in parallel via asyncio.gather(), manages state,
broadcasts agent activity to connected WebSocket clients.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable, Set

from agents import ScannerAgent, SignalAgent, RiskAgent, ExecutionAgent
from models import (
    AgentLogEntry, PortfolioState, ScannerOutput,
    SignalOutput, RiskOutput, ExecutionOutput, WSMessage
)
from config import settings
from polymarket_client import polymarket
import redis_client as rc


class Orchestrator:
    def __init__(self, broadcast: Callable[[dict], Awaitable[None]]):
        self.broadcast = broadcast
        self.scanner = ScannerAgent()
        self.signal = SignalAgent()
        self.risk = RiskAgent()
        self.execution = ExecutionAgent()

        self._running = False
        self._cycle_count = 0
        self._ws_clients: Set = set()

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self):
        self._running = True
        await self._log_system("System online — PAPER_TRADING=" + str(settings.paper_trading))

        # Initialize portfolio if not exists
        portfolio = await rc.get_portfolio()
        if not portfolio:
            portfolio = await rc.init_portfolio()
            await self._log_system(f"Portfolio initialized: ${portfolio.bankroll:.2f} bankroll")

        await self._emit("system_status", {
            "status": "ONLINE",
            "paper_trading": settings.paper_trading,
            "bankroll": portfolio.bankroll,
            "scan_interval": settings.scan_interval_seconds,
        })

        while self._running:
            cycle_start = asyncio.get_event_loop().time()
            try:
                await self._run_cycle()
            except Exception as e:
                await self._log_system(f"Cycle error: {e}", level="ERROR")

            self._cycle_count += 1
            elapsed = asyncio.get_event_loop().time() - cycle_start
            sleep_time = max(0, settings.scan_interval_seconds - elapsed)
            await asyncio.sleep(sleep_time)

    def stop(self):
        self._running = False

    # ─── Main Cycle ───────────────────────────────────────────────────────────

    async def _run_cycle(self):
        await self._log_system(f"Cycle #{self._cycle_count + 1} starting")
        await self._emit("cycle_start", {"cycle": self._cycle_count + 1})

        # ── Step 1: Fetch markets ──────────────────────────────────────────
        try:
            markets = await polymarket.get_top_markets_enriched(limit=500)
            await self._emit("markets_fetched", {"count": len(markets)})
        except Exception as e:
            await self._log_system(f"Failed to fetch markets: {e}", level="ERROR")
            markets = []

        if not markets:
            await self._log_system("No markets available — skipping cycle", level="WARN")
            return

        # ── Step 2: SCANNER ───────────────────────────────────────────────
        scan_result = await self.scanner.scan(markets)

        if not scan_result or not scan_result.opportunities:
            await self._log_system("No opportunities found this cycle")
            await self._emit("scan_complete", {"opportunities": 0})
            await self._update_portfolio_snapshot()
            return

        await self._emit("scan_complete", {
            "opportunities": len(scan_result.opportunities),
            "markets_scanned": scan_result.markets_scanned,
            "market_state": scan_result.market_state.model_dump(),
        })

        # Emit individual opportunities for signal rain
        for opp in scan_result.opportunities:
            await self._emit("opportunity", opp.model_dump())

        # ── Step 3: SIGNAL — run in parallel for all HIGH priority opps ──
        portfolio = await rc.get_portfolio()
        open_positions = await rc.get_open_positions()
        open_pos_dicts = [p.model_dump() for p in open_positions]

        # Select top opportunities by priority
        high_opps = [o for o in scan_result.opportunities if o.priority == "HIGH"]
        med_opps = [o for o in scan_result.opportunities if o.priority == "MEDIUM"]
        candidates = (high_opps + med_opps)[:3]  # analyze top 3 per cycle

        signal_tasks = [
            self.signal.analyze(opp, open_pos_dicts)
            for opp in candidates
        ]
        signal_results = await asyncio.gather(*signal_tasks, return_exceptions=True)

        # ── Step 4: Process each signal through RISK → EXECUTION ─────────
        for i, (opp, signal_result) in enumerate(zip(candidates, signal_results)):
            if isinstance(signal_result, Exception) or signal_result is None:
                continue

            signal: SignalOutput = signal_result
            await self._emit("signal", signal.model_dump())

            print(
                f"[ORCHESTRATOR] SIGNAL result: market={signal.market_id} "
                f"recommendation={signal.recommendation} conviction={signal.conviction} "
                f"direction={signal.direction} edge={signal.edge}"
            )
            await self._log_system(
                f"SIGNAL result: recommendation={signal.recommendation} "
                f"conviction={signal.conviction} direction={signal.direction} "
                f"edge={signal.edge:.3f} — {opp.question[:50]}",
                agent="SIGNAL"
            )

            if signal.recommendation not in ("TRADE",):
                await self._log_system(
                    f"SIGNAL gated: {signal.recommendation} (conviction={signal.conviction}, "
                    f"min_conviction={settings.min_conviction}) — {opp.question[:50]}",
                    agent="SIGNAL"
                )
                continue

            # ── RISK evaluation ─────────────────────────────────────────
            if not portfolio:
                portfolio = await rc.init_portfolio()

            session_stats = await rc.get_all_stats()
            risk_result = await self.risk.evaluate(
                signal, portfolio, open_pos_dicts, session_stats
            )

            if not risk_result:
                continue

            print(f"[RISK] Decision: {risk_result.decision} size={risk_result.approved_size} reason={risk_result.veto_reason}")
            await self._emit("risk", risk_result.model_dump())

            if risk_result.decision == "VETOED":
                continue

            # ── EXECUTION ───────────────────────────────────────────────
            exec_result = await self.execution.enter_trade(signal, risk_result)
            if exec_result:
                await self._emit("execution", exec_result.model_dump())
                await self._update_portfolio_after_trade(risk_result.approved_size, portfolio)

        # ── Step 5: Monitor existing positions ──────────────────────────
        if open_positions:
            await self._monitor_positions(open_positions, open_pos_dicts)

        # ── Step 6: Update portfolio snapshot ───────────────────────────
        await self._update_portfolio_snapshot()

    # ─── Position Monitoring ──────────────────────────────────────────────────

    async def _monitor_positions(self, open_positions, open_pos_dicts):
        monitor_results = await self.execution.monitor_positions(open_pos_dicts)
        for result in monitor_results:
            if result.action in ("EXIT", "ALERT"):
                await self._emit("execution", result.model_dump())
                if result.action == "EXIT":
                    await self._process_exit(result)

    async def _process_exit(self, exec_result: ExecutionOutput):
        """Close a position and update portfolio."""
        positions = await rc.get_open_positions()
        for pos in positions:
            if pos.market_id == exec_result.market_id:
                pos.status = "CLOSED"
                from datetime import datetime
                pos.closed_at = datetime.utcnow().isoformat()
                await rc.update_position(pos)

                portfolio = await rc.get_portfolio()
                if portfolio:
                    # Estimate P&L (simplified)
                    pnl = pos.unrealized_pnl
                    portfolio.session_pnl += pnl
                    portfolio.total_pnl += pnl
                    portfolio.deployed -= pos.size_usd
                    portfolio.available += pos.size_usd + pnl
                    portfolio.open_positions = max(0, portfolio.open_positions - 1)

                    if pnl > 0:
                        portfolio.winning_trades += 1
                        await rc.increment_stat("session_wins")
                        await rc.increment_stat("consecutive_losses", -float(await rc.get_stat("consecutive_losses")))
                    else:
                        await rc.increment_stat("session_losses")
                        await rc.increment_stat("consecutive_losses")

                    portfolio.total_trades += 1
                    if portfolio.total_trades > 0:
                        portfolio.win_rate = (portfolio.winning_trades / portfolio.total_trades) * 100

                    await rc.save_portfolio(portfolio)
                    await self._emit("portfolio", portfolio.model_dump())
                break

    # ─── Portfolio Helpers ────────────────────────────────────────────────────

    async def _update_portfolio_after_trade(self, size: float, portfolio: Optional[PortfolioState]):
        if not portfolio:
            return
        portfolio.deployed += size
        portfolio.available = max(0, portfolio.available - size)
        portfolio.open_positions += 1

        # Update session health
        drawdown_pct = abs(portfolio.session_pnl) / portfolio.bankroll * 100 if portfolio.session_pnl < 0 else 0
        portfolio.session_drawdown = drawdown_pct
        if drawdown_pct >= 20:
            portfolio.session_health = "RED"
        elif drawdown_pct >= 10:
            portfolio.session_health = "YELLOW"
        else:
            portfolio.session_health = "GREEN"

        await rc.save_portfolio(portfolio)
        await self._emit("portfolio", portfolio.model_dump())

    async def _update_portfolio_snapshot(self):
        portfolio = await rc.get_portfolio()
        if portfolio:
            await rc.record_pnl_snapshot(portfolio.session_pnl)
            await self._emit("portfolio", portfolio.model_dump())

    # ─── Event Emission ───────────────────────────────────────────────────────

    async def _emit(self, event_type: str, payload: dict):
        msg = WSMessage(type=event_type, payload=payload)
        try:
            await self.broadcast(msg.model_dump())
        except Exception:
            pass

    async def _log_system(self, message: str, level: str = "INFO", agent: str = "SYSTEM"):
        entry = AgentLogEntry(agent=agent, level=level, message=message)
        await rc.log_agent_event(entry)
        await self._emit("log", entry.model_dump())
