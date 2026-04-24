"""
WALLET TRACKER — Agent 5
Monitors smart wallet activity on Polymarket. No Claude API calls — pure on-chain logic.
Detects new trades by known profitable wallets and cluster entries (3+ wallets, same market).
Pushes signals to Redis queue; orchestrator routes them to RISK agent.
"""
import asyncio
import httpx
from datetime import datetime, timezone
from typing import Callable, Awaitable, Optional

import redis_client as rc
from models import AgentLogEntry, WSMessage

DATA_URL = "https://data-api.polymarket.com"
REQUEST_TIMEOUT = 10.0


class WalletTrackerAgent:
    name = "WALLET"

    LEADERBOARD_REFRESH_INTERVAL = 600  # refresh wallet list every 10 minutes
    POLL_INTERVAL = 60                  # poll each wallet's trades every 60 seconds
    CLUSTER_WINDOW_SECONDS = 300        # 5-minute window for cluster detection
    CLUSTER_MIN = 3                     # wallets needed for CLUSTER signal
    CLUSTER_STRONG = 5                  # wallets needed for STRONG_CLUSTER signal
    TOP_WALLETS = 20

    MAX_QUEUE_SIZE = 5

    def __init__(self, broadcast: Callable[[dict], Awaitable[None]]):
        self.broadcast = broadcast
        self._running = False
        # market_id -> list[{wallet, wallet_pnl, ts, direction, price, question}]
        self._recent_entries: dict[str, list[dict]] = {}
        self._last_leaderboard_refresh = 0.0
        # Session-level dedup: never re-signal a market_id once it has been emitted
        self._signalled_markets: set[str] = set()

    async def start(self):
        self._running = True
        await self._log("INFO", "Wallet tracker online — monitoring smart wallets")

        while self._running:
            try:
                now = asyncio.get_event_loop().time()

                if now - self._last_leaderboard_refresh > self.LEADERBOARD_REFRESH_INTERVAL:
                    await self._refresh_smart_wallets()
                    self._last_leaderboard_refresh = now

                await self._poll_wallet_trades()
                self._prune_stale_entries()

            except Exception as e:
                await self._log("ERROR", f"Wallet tracker cycle error: {e}")

            await asyncio.sleep(self.POLL_INTERVAL)

    def stop(self):
        self._running = False

    # ─── Leaderboard ──────────────────────────────────────────────────────────

    async def _refresh_smart_wallets(self):
        print(f"[WALLET] Fetching leaderboard from data-api.polymarket.com")
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as c:
                r = await c.get(
                    f"{DATA_URL}/v1/leaderboard",
                    params={"limit": 50, "orderBy": "PNL", "timePeriod": "ALL"},
                )
                print(f"[WALLET] Leaderboard response: {r.status_code}")
                r.raise_for_status()
                data = r.json()

            entries = data if isinstance(data, list) else data.get("data", [])
            print(f"[WALLET] Leaderboard raw entries: {len(entries)}")

            wallets = []
            for entry in entries:
                addr = entry.get("proxyWallet")
                if not addr or not str(addr).startswith("0x"):
                    continue
                pnl = float(entry.get("pnl") or 0)
                wallets.append({"address": str(addr), "pnl": pnl})
                if len(wallets) >= self.TOP_WALLETS:
                    break

            print(f"[WALLET] Loaded {len(wallets)} smart wallets")
            if wallets:
                await rc.set_smart_wallets(wallets)
                await self._log("INFO", f"Smart wallet list updated: {len(wallets)} wallets tracked")
            else:
                print(f"[WALLET] No valid 0x addresses found in leaderboard — sample: {entries[:2]}")
                await self._log("WARN", "Leaderboard returned no valid wallet addresses")

        except Exception as e:
            print(f"[WALLET] Error fetching leaderboard: {e}")
            await self._log("WARN", f"Leaderboard refresh failed: {e}")

    MAX_SIGNALS_PER_CYCLE = 3

    # ─── Trade Polling ────────────────────────────────────────────────────────

    async def _poll_wallet_trades(self):
        wallets = await rc.get_smart_wallets()
        if not wallets:
            print(f"[WALLET] No smart wallets in Redis yet — skipping trade poll")
            return

        print(f"[WALLET] Polling trades for {len(wallets)} smart wallets")
        tasks = [self._check_wallet_trades(w) for w in wallets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = sum(1 for r in results if isinstance(r, Exception))
        ok = len(wallets) - errors
        print(f"[WALLET] Trade poll complete: {ok}/{len(wallets)} wallets OK, {errors} errors")
        if errors:
            await self._log("WARN", f"Trade poll: {ok}/{len(wallets)} wallets responded")

        # Collect candidate signals returned from each wallet check
        candidates: list[dict] = []
        for r in results:
            if isinstance(r, list):
                candidates.extend(r)

        if not candidates:
            return

        # Deduplicate by market_id — keep the entry with the highest wallet_count
        best: dict[str, dict] = {}
        for sig in candidates:
            mid = sig["market_id"]
            if mid not in best or sig["wallet_count"] > best[mid]["wallet_count"]:
                best[mid] = sig

        # Rank by wallet_count DESC, then confidence DESC
        ranked = sorted(best.values(), key=lambda s: (s["wallet_count"], s["confidence"]), reverse=True)

        # Skip markets already sitting in the queue (prevents re-queuing same market)
        queued_ids = await rc.get_queued_wallet_market_ids()

        pushed = 0
        for sig in ranked:
            if pushed >= self.MAX_SIGNALS_PER_CYCLE:
                break

            mid = sig["market_id"]

            # Session-level dedup — never re-signal the same market
            if mid in self._signalled_markets:
                print(f"[WALLET] Session dedup: skipping already-signalled market={mid[:24]}")
                continue

            # Queue-level dedup — skip if market already sitting in queue
            if mid in queued_ids:
                print(f"[WALLET] Dedup: skipping already-queued market={mid[:24]}")
                continue

            # Hard queue cap — don't flood orchestrator
            queue_size = len(queued_ids)
            if queue_size >= self.MAX_QUEUE_SIZE:
                print(f"[WALLET] Queue size: {queue_size}, skipping")
                break

            await rc.push_wallet_signal(sig)
            self._signalled_markets.add(mid)
            queued_ids.add(mid)  # prevent double-push within same cycle
            pushed += 1

            log_msg = (
                f"[WALLET] {sig['signal_type']} market={mid[:24]} "
                f"wallets={sig['wallet_count']} confidence={sig['confidence']}"
            )
            await self._log("INFO", log_msg)
            print(f"[WALLET TRACKER] {log_msg} direction={sig['direction']}")
            try:
                await self.broadcast(WSMessage(type="wallet_signal", payload=sig).model_dump())
            except Exception:
                pass

        skipped = len(ranked) - pushed
        print(f"[WALLET] Emitted {pushed} signal(s) this cycle ({skipped} deduplicated/skipped)")

    async def _check_wallet_trades(self, wallet: dict) -> list[dict]:
        """Returns candidate signal dicts for new trades. Empty list if none or first poll."""
        address = wallet["address"]
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as c:
                r = await c.get(f"{DATA_URL}/trades", params={"maker": address, "limit": 10})
                r.raise_for_status()
                data = r.json()

            trades = data if isinstance(data, list) else data.get("history", data.get("trades", []))
            if not isinstance(trades, list):
                return []

        except Exception:
            return []

        def trade_id(t: dict) -> str:
            return str(
                t.get("id")
                or t.get("transactionHash")
                or f"{t.get('market','')}-{t.get('timestamp','')}-{t.get('price','')}"
            )

        known_ids = await rc.get_wallet_trade_ids(address)
        current_ids = {trade_id(t) for t in trades}

        # First poll — save baseline only, no signals
        if not known_ids:
            await rc.set_wallet_trade_ids(address, current_ids)
            print(f"[WALLET] Baseline set for {address[:10]}... ({len(current_ids)} trades)")
            return []

        new_trades = [t for t in trades if trade_id(t) not in known_ids]
        await rc.set_wallet_trade_ids(address, current_ids)

        signals = []
        for trade in new_trades:
            sig = self._build_signal(wallet, trade)
            if sig:
                signals.append(sig)
        return signals

    # ─── Signal Generation ────────────────────────────────────────────────────

    def _build_signal(self, wallet: dict, trade: dict) -> Optional[dict]:
        """Updates _recent_entries for cluster tracking and returns a signal dict."""
        market_id = str(
            trade.get("conditionId")
            or trade.get("market")
            or trade.get("market_id")
            or ""
        )
        if not market_id:
            return None

        question = str(
            trade.get("title")
            or trade.get("question")
            or trade.get("market_slug")
            or market_id[:40]
        )[:120]

        outcome = (trade.get("outcome") or "").upper()
        direction = "YES" if outcome == "YES" else "NO"
        price = float(trade.get("price") or 0)

        entry = {
            "wallet": wallet["address"],
            "wallet_pnl": wallet.get("pnl", 0),
            "ts": datetime.now(timezone.utc).timestamp(),
            "direction": direction,
            "price": price,
            "question": question,
        }

        if market_id not in self._recent_entries:
            self._recent_entries[market_id] = []
        self._recent_entries[market_id].append(entry)

        unique_wallets = list({e["wallet"] for e in self._recent_entries[market_id]})
        wallet_count = len(unique_wallets)
        avg_pnl = sum(e["wallet_pnl"] for e in self._recent_entries[market_id]) / max(len(self._recent_entries[market_id]), 1)

        if wallet_count >= self.CLUSTER_STRONG:
            signal_type = "STRONG_CLUSTER"
            confidence = 90
        elif wallet_count >= self.CLUSTER_MIN:
            signal_type = "CLUSTER"
            confidence = 75
        else:
            signal_type = "WALLET_COPY"
            confidence = 60

        return {
            "signal_type": signal_type,
            "market_id": market_id,
            "market_question": question,
            "direction": direction,
            "wallets_involved": unique_wallets,
            "wallet_count": wallet_count,
            "avg_wallet_pnl": round(avg_pnl, 2),
            "confidence": confidence,
            "entry_price": price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _prune_stale_entries(self):
        cutoff = datetime.now(timezone.utc).timestamp() - self.CLUSTER_WINDOW_SECONDS
        for market_id in list(self._recent_entries.keys()):
            self._recent_entries[market_id] = [
                e for e in self._recent_entries[market_id] if e["ts"] > cutoff
            ]
            if not self._recent_entries[market_id]:
                del self._recent_entries[market_id]

    async def _log(self, level: str, message: str, data: Optional[dict] = None):
        entry = AgentLogEntry(agent="WALLET", level=level, message=message, data=data)
        await rc.log_agent_event(entry)
