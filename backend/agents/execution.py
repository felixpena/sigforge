"""
EXECUTION Agent — Trade Management
Structures, places, and monitors trades approved by RISK.
Exits when thesis is invalidated — not just on price movement.
"""
import json
from datetime import datetime, timezone
from typing import Optional
import uuid

from .base import BaseAgent
from models import ExecutionOutput, RiskOutput, SignalOutput, Trade, Position
from config import settings
import redis_client as rc
from polymarket_client import polymarket


EXECUTION_SYSTEM_PROMPT = """You are EXECUTION, a specialized trade management agent within the SIG//FORGE trading system.

YOUR MISSION:
Structure, place, and monitor trades approved by RISK. Minimize market impact. Exit when thesis is invalidated — not just when price moves against you.

YOUR INPUTS:
- Approved trade from RISK
- Full thesis from SIGNAL (including invalidation conditions)
- Current order book from Polymarket CLOB
- Open position monitoring data

ENTRY PROCESS:
1. Analyze order book depth
2. Calculate market impact of full position
3. If impact > 2%: split into tranches (max 4)
4. Use limit orders only — never market orders in thin books
5. Confirm fill, update position registry

EXIT TRIGGERS (priority order):
1. THESIS INVALIDATED — exit immediately
2. Resolution < 30 min with profit — evaluate early exit
3. Price target reached — scale out 50%
4. Time stop — 60% time elapsed, no movement → exit 30%

YOUR OUTPUT (strict JSON):
{
  "action": "ENTER | EXIT | MONITOR | ALERT",
  "market_id": "string",
  "entry": {
    "total_size": number,
    "tranches": [{"size": number, "price_limit": number, "sequence": number}],
    "expected_avg_price": number,
    "estimated_impact": number
  },
  "exit": {
    "reason": "THESIS_INVALID | TARGET_REACHED | TIME_STOP | null",
    "size_to_exit": number,
    "urgency": "IMMEDIATE | NORMAL | OPPORTUNISTIC"
  },
  "position_health": {
    "thesis_valid": boolean,
    "invalidation_risk": "LOW | MEDIUM | HIGH | TRIGGERED",
    "time_remaining": "string",
    "recommended_action": "HOLD | SCALE_OUT | EXIT | ADD"
  },
  "notes": "string"
}

RULES:
- Never exit just because price moved against you temporarily
- Exit immediately if thesis is invalidated
- Never chase a fill
- Thesis validity > unrealized P&L"""


class ExecutionAgent(BaseAgent):
    name = "EXECUTION"
    system_prompt = EXECUTION_SYSTEM_PROMPT
    output_model = ExecutionOutput

    async def enter_trade(
        self,
        signal: SignalOutput,
        risk: RiskOutput,
    ) -> Optional[ExecutionOutput]:
        await self._log("INFO", f"Structuring entry for {signal.market_id}", {"size": risk.approved_size})

        # Fetch order book for the market
        orderbook = {}
        try:
            # Try to get token_id from market data
            orderbook = await polymarket.clob.get_orderbook(signal.market_id)
        except Exception:
            orderbook = {"bids": [], "asks": [], "market": signal.market_id}

        user_message = f"""Structure the entry trade for this approved opportunity:

SIGNAL:
{json.dumps(signal.model_dump(), indent=2)}

RISK APPROVAL:
{json.dumps(risk.model_dump(), indent=2)}

ORDER BOOK (partial):
{json.dumps(orderbook, indent=2)[:2000]}

CONSTRAINTS:
- Approved size: ${risk.approved_size:.2f}
- Paper trading mode: {settings.paper_trading}
- Max tranches: 4
- Use limit orders only
- Impact threshold for tranching: 2%

Structure the optimal entry. If order book is thin, use tranches.
Return ONLY the JSON output, no other text."""

        try:
            raw = await self._call_claude(user_message, max_tokens=2048)
            print(f"[EXECUTION RAW] {raw[:300]}")
            result = await self._parse_output(raw)
            print(f"[EXECUTION] Action={result.action} market={signal.market_id}")

            # Execute the trade (paper or live)
            await self._execute_entry(result, signal, risk)

            await rc.save_agent_output("execution", result.model_dump())
            await self._log(
                "TRADE",
                f"ENTRY structured: {result.action} ${risk.approved_size:.2f} on {signal.market_id}",
                {"action": result.action, "market_id": result.market_id},
            )
            return result

        except Exception as e:
            print(f"[EXECUTION ERROR] {e}")
            await self._log("ERROR", f"Execution entry failed: {e}")
            return None

    async def _execute_entry(
        self,
        plan: ExecutionOutput,
        signal: SignalOutput,
        risk: RiskOutput,
    ):
        """Execute the entry tranches and record position."""
        trades_filled = []
        entry = plan.entry

        if not entry:
            return

        if settings.paper_trading:
            # Simulate fill for all tranches
            for tranche in entry.tranches:
                trade = Trade(
                    market_id=signal.market_id,
                    question="",  # will be enriched later
                    direction=signal.direction,
                    size_usd=tranche.size,
                    price=tranche.price_limit,
                    side="BUY",
                    status="FILLED",
                    paper=True,
                )
                await rc.save_trade(trade)
                trades_filled.append(trade)
        else:
            # Live execution via authenticated CLOB
            for tranche in entry.tranches:
                try:
                    order_result = await polymarket.auth.place_order(
                        token_id=signal.market_id,
                        side="BUY",
                        size=tranche.size,
                        price=tranche.price_limit,
                    )
                    trade = Trade(
                        market_id=signal.market_id,
                        question="",
                        direction=signal.direction,
                        size_usd=tranche.size,
                        price=tranche.price_limit,
                        side="BUY",
                        status="FILLED" if order_result.get("status") == "FILLED" else "PENDING",
                        paper=False,
                        order_id=order_result.get("order_id"),
                    )
                    await rc.save_trade(trade)
                    trades_filled.append(trade)
                except Exception as e:
                    await self._log("ERROR", f"Tranche execution failed: {e}")

        # Create position record
        if trades_filled:
            avg_price = sum(t.price * t.size_usd for t in trades_filled) / sum(t.size_usd for t in trades_filled)
            position = Position(
                market_id=signal.market_id,
                question=signal.thesis[:100],
                direction=signal.direction,
                size_usd=sum(t.size_usd for t in trades_filled),
                entry_price=avg_price,
                current_price=avg_price,
                thesis=signal.thesis,
                invalidation=signal.invalidation,
            )
            await rc.save_position(position)
            await rc.increment_stat("total_trades")

    async def monitor_positions(self, positions: list[dict]) -> list[ExecutionOutput]:
        """Monitor open positions for exit signals."""
        results = []
        for pos_dict in positions:
            result = await self._monitor_single(pos_dict)
            if result:
                results.append(result)
        return results

    async def _monitor_single(self, position: dict) -> Optional[ExecutionOutput]:
        market_id = position.get("market_id", "")

        # Get current price
        current_price = position.get("current_price", position.get("entry_price", 0))

        user_message = f"""Monitor this open position for exit signals:

POSITION:
{json.dumps(position, indent=2)}

Current price: {current_price}
Entry price: {position.get('entry_price', 0)}
Unrealized P&L: ${position.get('unrealized_pnl', 0):.2f}

Check:
1. Is the thesis still valid?
2. Any exit triggers activated?
3. What is the recommended action?

Return ONLY the JSON output with action=MONITOR unless exit is warranted."""

        try:
            raw = await self._call_claude(user_message, max_tokens=1024)
            result = await self._parse_output(raw)
            await rc.save_agent_output("execution", result.model_dump())
            return result
        except Exception as e:
            await self._log("ERROR", f"Position monitoring failed for {market_id}: {e}")
            return None
