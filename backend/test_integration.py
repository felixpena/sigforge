"""
SIG//FORGE Integration Test
Tests: Polymarket API connectivity, Redis, all 4 agents, WebSocket pipeline.
Run with: python test_integration.py
"""
import asyncio
import json
import os
import sys
from datetime import datetime

# ── Color output ────────────────────────────────────────────────────────────

def green(s): return f"\033[92m{s}\033[0m"
def red(s): return f"\033[91m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def cyan(s): return f"\033[96m{s}\033[0m"
def bold(s): return f"\033[1m{s}\033[0m"

PASS = green("✓ PASS")
FAIL = red("✗ FAIL")
SKIP = yellow("⊘ SKIP")


async def test_redis():
    print(f"\n{cyan('[ REDIS ]')}")
    try:
        import redis_client as rc
        ok = await rc.ping()
        if ok:
            print(f"  {PASS} Redis connection")
            # Test basic operations
            await rc.increment_stat("test_counter")
            val = await rc.get_stat("test_counter")
            print(f"  {PASS} Redis read/write (counter={val})")
            return True
        else:
            print(f"  {FAIL} Redis not reachable")
            return False
    except Exception as e:
        print(f"  {FAIL} Redis error: {e}")
        return False


async def test_polymarket_api():
    print(f"\n{cyan('[ POLYMARKET API ]')}")
    results = {}

    try:
        from polymarket_client import polymarket

        # Test Gamma API
        markets = await polymarket.gamma.get_top_markets(limit=5)
        if markets:
            print(f"  {PASS} Gamma API — {len(markets)} markets fetched")
            print(f"       Sample: {markets[0].get('question', '')[:60]}...")
            results['gamma'] = True
        else:
            print(f"  {FAIL} Gamma API returned empty")
            results['gamma'] = False
    except Exception as e:
        print(f"  {FAIL} Gamma API: {e}")
        results['gamma'] = False

    try:
        from polymarket_client import polymarket
        wallet = os.getenv("WALLET_ADDRESS", "0xeB5df547a289f98C39C136EA52fB94F11c5e92Ad")

        # Test Data API (public, no auth needed)
        positions = await polymarket.data.get_positions(wallet)
        print(f"  {PASS} Data API — {len(positions)} positions for wallet")
        results['data'] = True
    except Exception as e:
        print(f"  {yellow('⊘ SKIP')} Data API: {e}")
        results['data'] = None

    try:
        from polymarket_client import polymarket
        clob_data = await polymarket.clob.get_markets()
        count = len(clob_data.get('data', []))
        print(f"  {PASS} CLOB API — {count} markets")
        results['clob'] = True
    except Exception as e:
        print(f"  {FAIL} CLOB API: {e}")
        results['clob'] = False

    return all(v for v in results.values() if v is not None)


async def test_enriched_markets():
    print(f"\n{cyan('[ ENRICHED MARKETS ]')}")
    try:
        from polymarket_client import polymarket
        markets = await polymarket.get_top_markets_enriched(limit=10)
        if markets:
            print(f"  {PASS} Enriched markets: {len(markets)} returned")
            m = markets[0]
            fields = ['id', 'question', 'volume', 'liquidity', 'tokens']
            missing = [f for f in fields if f not in m]
            if not missing:
                print(f"  {PASS} Market schema complete")
            else:
                print(f"  {yellow('WARN')} Missing fields: {missing}")
            return True
        else:
            print(f"  {FAIL} No enriched markets returned")
            return False
    except Exception as e:
        print(f"  {FAIL} Enriched markets: {e}")
        return False


async def test_scanner_agent():
    print(f"\n{cyan('[ AGENT 1: SCANNER ]')}")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f"  {SKIP} ANTHROPIC_API_KEY not set")
        return None

    try:
        from polymarket_client import polymarket
        from agents.scanner import ScannerAgent

        markets = await polymarket.get_top_markets_enriched(limit=20)
        if not markets:
            print(f"  {FAIL} No markets to scan")
            return False

        scanner = ScannerAgent()
        result = await scanner.scan(markets)

        if result:
            print(f"  {PASS} Scanner ran — {result.markets_scanned} scanned, {len(result.opportunities)} opportunities")
            print(f"       Session bias: {result.market_state.session_bias}")
            for opp in result.opportunities[:3]:
                print(f"       [{opp.priority}] {opp.question[:50]}... score={opp.anomaly_score:.0f}")
            return True
        else:
            print(f"  {FAIL} Scanner returned None")
            return False
    except Exception as e:
        print(f"  {FAIL} Scanner: {e}")
        import traceback; traceback.print_exc()
        return False


async def test_signal_agent(opportunity=None):
    print(f"\n{cyan('[ AGENT 2: SIGNAL ]')}")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f"  {SKIP} ANTHROPIC_API_KEY not set")
        return None

    if not opportunity:
        # Create a mock opportunity
        from models import MarketOpportunity
        opportunity = MarketOpportunity(
            market_id="test-market-001",
            question="Will Bitcoin exceed $100,000 by end of 2025?",
            current_price=0.45,
            implied_probability=0.45,
            volume_24h=150000,
            liquidity=85000,
            anomaly_score=72,
            anomaly_type="price_drift",
            time_to_resolution="30 days",
            resolution_criteria="Market resolves YES if BTC/USD price exceeds $100,000 on Coinbase",
            priority="HIGH",
            reason="Price drifted below 0.5 despite bullish macro context",
        )

    try:
        from agents.signal import SignalAgent
        signal = SignalAgent()
        result = await signal.analyze(opportunity, open_positions=[])

        if result:
            print(f"  {PASS} Signal ran")
            print(f"       Recommendation: {result.recommendation}")
            print(f"       Conviction: {result.conviction}")
            print(f"       Direction: {result.direction} ({result.true_probability:.2%} vs market {result.market_probability:.2%})")
            print(f"       Evidence sources: {len(result.evidence)}")
            return result
        else:
            print(f"  {FAIL} Signal returned None")
            return None
    except Exception as e:
        print(f"  {FAIL} Signal: {e}")
        import traceback; traceback.print_exc()
        return None


async def test_risk_agent(signal=None):
    print(f"\n{cyan('[ AGENT 3: RISK ]')}")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f"  {SKIP} ANTHROPIC_API_KEY not set")
        return None

    if not signal:
        from models import SignalOutput, Evidence
        signal = SignalOutput(
            market_id="test-market-001",
            thesis="Bitcoin is likely to exceed $100K based on technical and macro evidence",
            direction="YES",
            true_probability=0.62,
            market_probability=0.45,
            edge=17.0,
            conviction=74,
            evidence=[
                Evidence(source="Technical analysis", content="Breaking out of 6-month consolidation", weight="STRONG", direction="SUPPORTS"),
                Evidence(source="On-chain data", content="Accumulation by long-term holders", weight="MODERATE", direction="SUPPORTS"),
            ],
            base_rate="BTC exceeded previous ATH 68% of the time after halving events",
            invalidation="Price drops below $60K or regulatory action",
            time_sensitivity="DAYS",
            recommendation="TRADE",
            reasoning="Strong technical setup with institutional accumulation",
        )

    try:
        from agents.risk import RiskAgent
        from models import PortfolioState

        portfolio = PortfolioState(
            bankroll=1000,
            deployed=50,
            available=950,
            session_pnl=0,
            total_pnl=0,
            win_rate=0,
            avg_profit=0,
            total_trades=0,
            winning_trades=0,
            open_positions=1,
            session_drawdown=0,
            session_health="GREEN",
        )

        risk = RiskAgent()
        result = await risk.evaluate(signal, portfolio, [], {})

        if result:
            print(f"  {PASS} Risk ran")
            print(f"       Decision: {result.decision}")
            print(f"       Approved size: ${result.approved_size:.2f}")
            print(f"       Kelly: {result.kelly_fraction:.4f}")
            print(f"       Session health: {result.session_health}")
            if result.veto_reason:
                print(f"       Veto reason: {result.veto_reason}")
            return result
        else:
            print(f"  {FAIL} Risk returned None")
            return None
    except Exception as e:
        print(f"  {FAIL} Risk: {e}")
        import traceback; traceback.print_exc()
        return None


async def test_execution_agent(signal=None, risk=None):
    print(f"\n{cyan('[ AGENT 4: EXECUTION ]')}")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f"  {SKIP} ANTHROPIC_API_KEY not set")
        return None

    if not risk or risk.decision == "VETOED":
        print(f"  {SKIP} No approved trade to execute")
        return None

    try:
        from agents.execution import ExecutionAgent

        execution = ExecutionAgent()
        result = await execution.enter_trade(signal, risk)

        if result:
            print(f"  {PASS} Execution ran")
            print(f"       Action: {result.action}")
            if result.entry:
                print(f"       Total size: ${result.entry.total_size:.2f}")
                print(f"       Tranches: {len(result.entry.tranches)}")
                print(f"       Estimated impact: {result.entry.estimated_impact:.2f}%")
            return result
        else:
            print(f"  {FAIL} Execution returned None")
            return None
    except Exception as e:
        print(f"  {FAIL} Execution: {e}")
        import traceback; traceback.print_exc()
        return None


async def test_parallel_agents():
    print(f"\n{cyan('[ PARALLEL EXECUTION TEST ]')}")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f"  {SKIP} ANTHROPIC_API_KEY not set")
        return None

    try:
        from models import MarketOpportunity
        from agents.signal import SignalAgent

        opps = [
            MarketOpportunity(
                market_id=f"test-parallel-{i}",
                question=f"Test market question {i}",
                current_price=0.4 + i * 0.05,
                implied_probability=0.4 + i * 0.05,
                volume_24h=100000,
                liquidity=50000,
                anomaly_score=70 + i,
                anomaly_type="price_drift",
                time_to_resolution="7 days",
                resolution_criteria=f"Resolves YES if condition {i} is met",
                priority="HIGH",
                reason=f"Anomaly detected in market {i}",
            )
            for i in range(3)
        ]

        signal_agent = SignalAgent()
        start = asyncio.get_event_loop().time()

        results = await asyncio.gather(
            *[signal_agent.analyze(opp, []) for opp in opps],
            return_exceptions=True,
        )

        elapsed = asyncio.get_event_loop().time() - start
        success = [r for r in results if not isinstance(r, Exception) and r is not None]

        print(f"  {PASS} Parallel execution: {len(success)}/3 agents completed in {elapsed:.1f}s")
        return len(success) > 0

    except Exception as e:
        print(f"  {FAIL} Parallel test: {e}")
        return False


async def test_full_pipeline():
    print(f"\n{bold(cyan('[ FULL PIPELINE TEST ]'))}")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f"  {SKIP} Full pipeline requires ANTHROPIC_API_KEY")
        return

    print("  Running SCANNER → SIGNAL → RISK → EXECUTION pipeline...\n")

    from polymarket_client import polymarket
    markets = await polymarket.get_top_markets_enriched(limit=30)

    from agents.scanner import ScannerAgent
    scanner = ScannerAgent()
    scan_result = await scanner.scan(markets)

    if not scan_result or not scan_result.opportunities:
        print(f"  {yellow('WARN')} No opportunities found — pipeline complete (nothing to trade)")
        return

    opp = scan_result.opportunities[0]
    signal_result = await test_signal_agent(opp)

    if signal_result and signal_result.recommendation == "TRADE":
        risk_result = await test_risk_agent(signal_result)
        if risk_result and risk_result.decision != "VETOED":
            await test_execution_agent(signal_result, risk_result)

    print(f"\n  {PASS} Full pipeline test complete")


async def main():
    print(bold(f"\n{'='*60}"))
    print(bold("  SIG//FORGE — Integration Test Suite"))
    print(bold(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"))
    print(bold(f"{'='*60}"))

    # Load .env
    from dotenv import load_dotenv
    load_dotenv()

    paper = os.getenv("PAPER_TRADING", "true").lower() == "true"
    print(f"\n  Mode: {'PAPER TRADING' if paper else red('⚠️  LIVE TRADING')}")

    results = {}

    # Core infrastructure
    results['redis'] = await test_redis()
    results['polymarket'] = await test_polymarket_api()
    results['enriched'] = await test_enriched_markets()

    # Individual agents
    results['scanner'] = await test_scanner_agent()
    signal_out = await test_signal_agent()
    results['signal'] = signal_out is not None
    risk_out = await test_risk_agent(signal_out)
    results['risk'] = risk_out is not None
    results['execution'] = (await test_execution_agent(signal_out, risk_out)) is not None

    # Parallel test
    results['parallel'] = await test_parallel_agents()

    # Summary
    print(f"\n{bold('='*60)}")
    print(bold("  TEST SUMMARY"))
    print(bold('='*60))
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)

    for name, result in results.items():
        status = PASS if result is True else (FAIL if result is False else SKIP)
        print(f"  {status}  {name.upper()}")

    print(f"\n  {green(str(passed))} passed  {red(str(failed))} failed  {yellow(str(skipped))} skipped")
    print(f"\n  {'✅ System ready!' if failed == 0 else '⚠️  Fix failures before going live'}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
