"""
SIGNAL Agent — Research & Reasoning
Takes market anomalies and determines if they represent genuine mispricings.
Uses web_search tool via Claude to gather evidence.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from .base import BaseAgent
from models import SignalOutput, MarketOpportunity
from config import settings
import redis_client as rc


SIGNAL_SYSTEM_PROMPT = """You are SIGNAL, a specialized research and reasoning agent within the SIG//FORGE trading system.

YOUR MISSION:
Take market anomalies identified by SCANNER and determine if they represent genuine mispricings with a tradeable edge.

YOUR INPUTS:
- Opportunity data from SCANNER
- Real-time news via web search tool
- Historical resolution patterns
- Current session context and open positions

YOUR ANALYSIS PROCESS:
1. Read the resolution criteria EXACTLY
2. Search for recent information directly relevant to this market
3. Assess the BASE RATE — historically, how often do events like this resolve YES?
4. Identify what the market is pricing vs what evidence suggests
5. Stress test your thesis — what would make you wrong?
6. Generate conviction score based on evidence quality

CONVICTION FRAMEWORK:
- 90-100: Multiple strong signals, clear mispricing
- 70-89: Good evidence, reasonable edge
- 50-69: Marginal edge, minimum size only
- Below 50: No trade
- VETO: Active evidence AGAINST the thesis

YOUR OUTPUT (strict JSON):
{
  "market_id": "string",
  "thesis": "string",
  "direction": "YES | NO",
  "true_probability": number,
  "market_probability": number,
  "edge": number,
  "conviction": number,
  "evidence": [
    {
      "source": "string",
      "content": "string",
      "weight": "STRONG | MODERATE | WEAK",
      "direction": "SUPPORTS | CONTRADICTS"
    }
  ],
  "base_rate": "string",
  "invalidation": "string",
  "time_sensitivity": "IMMEDIATE | HOURS | DAYS",
  "recommendation": "TRADE | MONITOR | PASS | VETO",
  "reasoning": "string"
}

RULES:
- Never recommend TRADE with conviction below 65
- If resolution criteria is ambiguous — PASS
- Search at least 3 independent sources before TRADE
- Never ignore contradicting evidence
- Your job is to find reasons NOT to trade. If you can't find them, trade."""


# web_search tool definition for Claude
WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": "Search the web for current information about a topic",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query"
            }
        },
        "required": ["query"]
    }
}


class SignalAgent(BaseAgent):
    name = "SIGNAL"
    system_prompt = SIGNAL_SYSTEM_PROMPT
    output_model = SignalOutput

    async def analyze(
        self,
        opportunity: MarketOpportunity,
        open_positions: list[dict],
    ) -> Optional[SignalOutput]:
        await self._log("INFO", f"Analyzing: {opportunity.question[:60]}...", {"market_id": opportunity.market_id})

        context = {
            "opportunity": opportunity.model_dump(),
            "open_positions_count": len(open_positions),
            "open_position_market_ids": [p.get("market_id") for p in open_positions],
            "current_time_utc": datetime.now(timezone.utc).isoformat(),
        }

        user_message = f"""Analyze this market opportunity from SCANNER:

OPPORTUNITY DATA:
{json.dumps(opportunity.model_dump(), indent=2)}

SESSION CONTEXT:
- Open positions: {len(open_positions)}
- Current UTC time: {datetime.now(timezone.utc).isoformat()}

Instructions:
1. Research this market question using available information
2. Assess whether the current price ({opportunity.current_price}) is mispriced
3. Consider the anomaly type: {opportunity.anomaly_type} (score: {opportunity.anomaly_score})
4. Look for 3+ independent evidence sources
5. Apply strict rules: PASS if ambiguous, VETO if contradicting evidence is strong

Return ONLY the JSON output, no other text."""

        try:
            raw = await self._call_claude(user_message, max_tokens=4096)
            result = await self._parse_output(raw)

            # Enforce conviction floor
            if result.conviction < settings.min_conviction and result.recommendation == "TRADE":
                result = SignalOutput(
                    **{**result.model_dump(), "recommendation": "PASS"}
                )

            await rc.save_agent_output("signal", result.model_dump())
            await rc.save_signal(result.model_dump())
            await rc.increment_stat("total_signals")

            level = "TRADE" if result.recommendation == "TRADE" else "INFO"
            await self._log(
                level,
                f"Signal: {result.recommendation} | {opportunity.question[:50]} | conviction={result.conviction}",
                {"market_id": result.market_id, "recommendation": result.recommendation, "conviction": result.conviction},
            )
            return result

        except Exception as e:
            await self._log("ERROR", f"Signal analysis failed: {e}")
            return None
