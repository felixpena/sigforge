"""
SCANNER Agent — Market Intelligence
Monitors prediction markets in real-time and identifies anomalies.
"""
import json
import traceback
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
- Maximum 5 opportunities per scan
- Be conservative. A missed opportunity is better than a false signal.

OUTPUT FORMAT:
- Return ONLY a raw JSON object — no markdown, no code fences, no explanation
- Do not wrap the JSON in ```json or ``` blocks
- The very first character of your response must be { and the last must be }"""


class ScannerAgent(BaseAgent):
    name = "SCANNER"
    system_prompt = SCANNER_SYSTEM_PROMPT
    output_model = ScannerOutput

    async def scan(self, markets: list[dict]) -> Optional[ScannerOutput]:
        await self._log("INFO", f"Starting scan of {len(markets)} markets")

        # Pre-filter: active markets with sufficient liquidity only
        eligible = [
            m for m in markets
            if not m.get("closed", False)
            and m.get("active", True)
            and float(m.get("liquidity", 0) or 0) >= settings.min_liquidity_usd
        ]

        # Sort by liquidity desc so the best markets go to Claude first
        eligible.sort(key=lambda m: float(m.get("liquidity", 0) or 0), reverse=True)

        await self._log(
            "INFO",
            f"Pre-filter: {len(eligible)}/{len(markets)} markets eligible "
            f"(liquidity ≥ ${settings.min_liquidity_usd:,.0f}, active)",
        )

        # Category diversity: prioritize political/economic/crypto/regulatory, cap sports at 20%
        _PRIORITY_CATS = {"political", "politics", "economic", "economics", "crypto",
                          "cryptocurrency", "regulatory", "regulation", "finance"}
        _SPORTS_CATS = {"sports", "sport"}
        _SPORTS_CAP = 20

        priority_markets, sports_markets, other_markets = [], [], []
        for m in eligible:
            cat = (m.get("category") or "").lower()
            if any(kw in cat for kw in _PRIORITY_CATS):
                priority_markets.append(m)
            elif any(kw in cat for kw in _SPORTS_CATS):
                sports_markets.append(m)
            else:
                other_markets.append(m)

        # Fill 100 slots: priority first, then other, then sports (capped at 20)
        diverse: list[dict] = []
        diverse.extend(priority_markets[:100])
        slots = 100 - len(diverse)
        if slots > 0:
            diverse.extend(other_markets[:slots])
        slots = 100 - len(diverse)
        if slots > 0:
            diverse.extend(sports_markets[: min(_SPORTS_CAP, slots)])

        # Re-sort the selected set by liquidity
        diverse.sort(key=lambda m: float(m.get("liquidity", 0) or 0), reverse=True)

        await self._log(
            "INFO",
            f"Category mix: {len(priority_markets)} priority, {len(other_markets)} other, "
            f"{len(sports_markets)} sports → {len(diverse)} diverse markets selected",
        )

        # Build minimal summaries — only fields Claude needs
        market_summaries = []
        for m in diverse[:100]:  # cap at 100 to stay within Claude token limits
            tokens = m.get("tokens", [])
            yes_price = next(
                (t["price"] for t in tokens if t.get("outcome", "").upper() == "YES"), None
            )
            if yes_price is None and tokens:
                yes_price = tokens[0].get("price", 0)

            market_summaries.append({
                "market_id": m.get("id", ""),
                "question": m.get("question", "")[:100],
                "category": m.get("category", ""),
                "price": round(float(yes_price or 0), 4),
                "volume_24h": round(float(m.get("volume_24h", 0) or 0), 2),
                "liquidity": round(float(m.get("liquidity", 0) or 0), 2),
                "end_date": m.get("end_date") or "unknown",
            })

        user_message = f"""Current UTC timestamp: {datetime.now(timezone.utc).isoformat()}

MARKET DATA ({len(market_summaries)} markets, pre-filtered by liquidity ≥ ${settings.min_liquidity_usd:,.0f}):
{json.dumps(market_summaries, indent=2)}

Analyze these markets for anomalies. Apply all rules strictly.
Minimum anomaly score: {settings.min_anomaly_score}
Maximum opportunities: {settings.max_opportunities_per_scan}

Return ONLY the JSON output, no other text."""

        payload_chars = len(user_message)
        payload_markets = len(market_summaries)
        print(f"[SCANNER] Sending {payload_markets} markets to Claude ({payload_chars:,} chars)")

        try:
            raw = await self._call_claude(user_message, max_tokens=2048)
            print(f"[SCANNER RAW] {raw[:500]}")
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
            exc_type = type(e).__name__
            exc_msg = str(e)

            # Extract full details from Anthropic API errors
            status_code = getattr(e, "status_code", None)
            response_body = getattr(e, "response", None)
            error_body = None
            if response_body is not None:
                try:
                    error_body = response_body.json()
                except Exception:
                    error_body = str(response_body)

            print(f"[SCANNER ERROR] {exc_type}: {exc_msg}")
            print(f"[SCANNER ERROR] status_code={status_code}")
            print(f"[SCANNER ERROR] response_body={error_body}")
            print(f"[SCANNER ERROR] payload_markets={payload_markets}, payload_chars={payload_chars:,}")
            print(f"[SCANNER ERROR] Full traceback:\n{traceback.format_exc()}")

            await self._log(
                "ERROR",
                f"Scanner failed: [{exc_type}] {exc_msg} | status={status_code} | markets={payload_markets} chars={payload_chars:,}",
            )
            return None
