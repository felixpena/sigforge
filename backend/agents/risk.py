"""
RISK Agent — Capital Protection
Approves, resizes, or vetoes every trade recommendation from SIGNAL.
Implements Kelly Criterion with strict drawdown limits.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from .base import BaseAgent
from models import RiskOutput, SignalOutput, PortfolioState
from config import settings
import redis_client as rc


RISK_SYSTEM_PROMPT = """You are RISK, a specialized capital protection agent within the SIG//FORGE trading system.

YOUR MISSION:
Protect the bankroll. Approve, resize, or veto every trade recommendation from SIGNAL.

YOUR INPUTS:
- Trade recommendation from SIGNAL
- Current portfolio state (open positions, deployed capital, P&L)
- Bankroll and risk parameters
- Correlation matrix of open positions

KELLY CRITERION:
f = (bp - q) / b
where b = odds, p = true probability, q = 1-p
Never use full Kelly — max 25% Kelly

SIZING TIERS:
- Conviction 90-100 + Edge > 15%: 25% Kelly
- Conviction 75-89 + Edge > 10%: 15% Kelly
- Conviction 65-74 + Edge > 7%: 8% Kelly
- Below thresholds: VETO

VETO CONDITIONS (automatic, no exceptions):
- Conviction < 65
- Edge < 5%
- Insufficient liquidity for position size
- Position > 40% of bankroll
- 3 consecutive losses in same category
- Session drawdown > 20%

YOUR OUTPUT (strict JSON):
{
  "market_id": "string",
  "decision": "APPROVED | RESIZED | VETOED",
  "original_size": number,
  "approved_size": number,
  "kelly_fraction": number,
  "portfolio_concentration_after": number,
  "correlation_risk": "LOW | MEDIUM | HIGH",
  "veto_reason": "string | null",
  "resize_reason": "string | null",
  "risk_delta": "COOLING | NEUTRAL | HEATING",
  "session_health": "GREEN | YELLOW | RED",
  "notes": "string"
}

RULES:
- When in doubt — VETO
- Session health RED = no new positions
- A VETO is not a failure. It is the system working correctly."""


class RiskAgent(BaseAgent):
    name = "RISK"
    system_prompt = RISK_SYSTEM_PROMPT
    output_model = RiskOutput

    def _calculate_kelly(self, true_prob: float, price: float) -> tuple[float, float]:
        """Calculate Kelly fraction and recommended bet size."""
        if price <= 0 or price >= 1:
            return 0.0, 0.0
        # b = odds paid on win (price is already implied prob for binary market)
        # For a YES bet at price p: b = (1-p)/p
        b = (1.0 - price) / price
        p = true_prob
        q = 1.0 - p
        kelly = (b * p - q) / b if b > 0 else 0.0
        return max(0.0, kelly), b

    async def evaluate(
        self,
        signal: SignalOutput,
        portfolio: PortfolioState,
        open_positions: list[dict],
        session_stats: dict,
    ) -> Optional[RiskOutput]:
        await self._log("INFO", f"Evaluating risk for: {signal.market_id}", {"conviction": signal.conviction})

        kelly_fraction, odds = self._calculate_kelly(
            signal.true_probability,
            signal.market_probability,
        )

        # Compute suggested size before sending to Claude
        kelly_tiers = [
            (90, 0.15, 0.25),
            (75, 0.10, 0.15),
            (65, 0.07, 0.08),
        ]
        kelly_multiplier = 0.0
        for min_conviction, min_edge, multiplier in kelly_tiers:
            if signal.conviction >= min_conviction and signal.edge / 100.0 >= min_edge:
                kelly_multiplier = multiplier
                break

        suggested_size = round(portfolio.available * kelly_fraction * kelly_multiplier, 2)
        max_allowed = min(
            settings.max_position_size_usd,
            portfolio.bankroll * 0.40,
        )

        context = {
            "signal": signal.model_dump(),
            "portfolio": portfolio.model_dump(),
            "open_positions_count": len(open_positions),
            "session_stats": session_stats,
            "calculated_kelly": round(kelly_fraction, 4),
            "calculated_odds": round(odds, 4),
            "suggested_size_usd": suggested_size,
            "max_allowed_size_usd": max_allowed,
            "paper_trading": settings.paper_trading,
            "current_time_utc": datetime.now(timezone.utc).isoformat(),
        }

        user_message = f"""Evaluate this trade for risk approval:

SIGNAL RECOMMENDATION:
{json.dumps(signal.model_dump(), indent=2)}

PORTFOLIO STATE:
{json.dumps(portfolio.model_dump(), indent=2)}

RISK CALCULATIONS:
- Kelly fraction: {kelly_fraction:.4f}
- Suggested size: ${suggested_size:.2f}
- Max allowed size: ${max_allowed:.2f}
- Session drawdown: {portfolio.session_drawdown:.1f}%
- Consecutive losses tracked: {session_stats.get('consecutive_losses', 0)}
- Open positions: {len(open_positions)}

Apply ALL veto conditions strictly. If session_health is RED, veto.
If conviction < 65 or edge < 5%, veto immediately.

Return ONLY the JSON output, no other text."""

        try:
            raw = await self._call_claude(user_message, max_tokens=2048)
            result = await self._parse_output(raw)

            await rc.save_agent_output("risk", result.model_dump())

            if result.decision == "VETOED":
                await rc.increment_stat("total_vetoes")
                await self._log(
                    "VETO",
                    f"VETOED: {signal.market_id} — {result.veto_reason}",
                    {"market_id": signal.market_id, "reason": result.veto_reason},
                )
            else:
                await self._log(
                    "INFO",
                    f"{result.decision}: ${result.approved_size:.2f} for {signal.market_id}",
                    {"market_id": signal.market_id, "size": result.approved_size},
                )

            return result

        except Exception as e:
            await self._log("ERROR", f"Risk evaluation failed: {e}")
            return None
