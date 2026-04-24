"""
SCANNER Agent — Market Intelligence
Monitors prediction markets in real-time and identifies anomalies.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from .base import BaseAgent
from models import ScannerOutput, MarketOpportunity, MarketState
from config import settings
import redis_client as rc


SCANNER_SYSTEM_PROMPT = """You are SCANNER, a specialized market intelligence agent operating within the SIG//FORGE trading system.

YOUR MISSION:
Monitor prediction markets in real-time and identify anomalies where price does not reflect available information.

YOUR INPUTS:
- Live market data from Polymarket CLOB API (prices, volume, liquidity, time to resolution)
- Market metadata (resolution criteria, category, created date)
- Current timestamp and session context

YOUR ANALYSIS PROCESS:
1. Calculate implied probability from current market price
2. Compare volume and liquidity against 24h baseline
3. Flag markets where price moved > 2σ without obvious cause
4. Prioritize by: liquidity depth, time to resolution, category relevance
5. Identify correlated markets (same underlying event, different questions)

YOUR OUTPUT (strict JSON):
{
  "scan_timestamp": "ISO timestamp",
  "markets_scanned": number,
  "opportunities": [
    {
      "market_id": "string",
      "question": "string",
      "current_price": number,
      "implied_probability": number,
      "volume_24h": number,
      "liquidity": number,
      "anomaly_score": number (0-100),
      "anomaly_type": "price_drift | volume_spike | liquidity_gap | correlation_divergence",
      "time_to_resolution": "string",
      "resolution_criteria": "string",
      "priority": "HIGH | MEDIUM | LOW",
      "reason": "string"
    }
  ],
  "market_state": {
    "total_volume_session": number,
    "avg_liquidity": number,
    "dominant_category": "string",
    "session_bias": "RISK_ON | RISK_OFF | NEUTRAL"
  }
}

RULES:
- Only flag opportunities with anomaly_score > 65
- Never flag markets with liquidity < $5,000
- Never flag markets resolving in < 2 hours
- Maximum 12 opportunities per scan
- Be conservative. A missed opportunity is better than a false signal."""


class ScannerAgent(BaseAgent):
    name = "SCANNER"
    system_prompt = SCANNER_SYSTEM_PROMPT
    output_model = ScannerOutput

    async def scan(self, markets: list[dict]) -> Optional[ScannerOutput]:
        await self._log("INFO", f"Starting scan of {len(markets)} markets")

        # Build compact market summary for Claude
        market_summaries = []
        for m in markets[:500]:  # scan full market universe
            end_date = m.get("end_date", "unknown")
            tokens = m.get("tokens", [])
            yes_price = next((t["price"] for t in tokens if t.get("outcome", "").upper() == "YES"), None)
            no_price = next((t["price"] for t in tokens if t.get("outcome", "").upper() == "NO"), None)

            if yes_price is None and tokens:
                yes_price = tokens[0].get("price", 0)
            if no_price is None and len(tokens) > 1:
                no_price = tokens[1].get("price", 0)

            summary = {
                "id": m.get("id", ""),
                "question": m.get("question", "")[:120],
                "category": m.get("category", ""),
                "yes_price": round(float(yes_price or 0), 4),
                "no_price": round(float(no_price or 0), 4),
                "volume_24h": round(float(m.get("volume_24h", 0) or 0), 2),
                "liquidity": round(float(m.get("liquidity", 0) or 0), 2),
                "end_date": end_date,
                "description": (m.get("description", "") or "")[:100],
            }
            market_summaries.append(summary)

        user_message = f"""Current UTC timestamp: {datetime.now(timezone.utc).isoformat()}

MARKET DATA ({len(market_summaries)} markets):
{json.dumps(market_summaries, indent=2)}

Analyze these markets for anomalies. Apply all rules strictly.
Minimum liquidity: ${settings.min_liquidity_usd:,.0f}
Minimum anomaly score: {settings.min_anomaly_score}
Maximum opportunities: {settings.max_opportunities_per_scan}

Return ONLY the JSON output, no other text."""

        try:
            raw = await self._call_claude(user_message, max_tokens=4096)
            result = await self._parse_output(raw)

            # Filter by thresholds (enforce rules server-side)
            filtered_opps = [
                o for o in result.opportunities
                if o.anomaly_score >= settings.min_anomaly_score
                and o.liquidity >= settings.min_liquidity_usd
            ][:settings.max_opportunities_per_scan]

            result = ScannerOutput(
                scan_timestamp=result.scan_timestamp,
                markets_scanned=result.markets_scanned,
                opportunities=filtered_opps,
                market_state=result.market_state,
            )

            await rc.save_agent_output("scanner", result.model_dump())
            await rc.save_scan_result(result.model_dump())
            await rc.increment_stat("total_scans")
            await self._log(
                "INFO",
                f"Scan complete — {len(filtered_opps)} opportunities found",
                {"opportunities": len(filtered_opps), "markets_scanned": result.markets_scanned},
            )
            return result

        except Exception as e:
            await self._log("ERROR", f"Scanner failed: {e}")
            return None
