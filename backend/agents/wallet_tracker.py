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

    def __init__(self, broadcast: Callable[[dict], Awaitable[None]]):
        self.broadcast = broadcast
        self._running = False
        # market_id -> list[{wallet, wallet_pnl, ts, direction, price, question}]
        self._recent_entries: dict[str, list[dict]] = {}
        self._last_leaderboard_refresh = 0.0

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

    async def _check_wallet_trades(self, wallet: dict):
        address = wallet["address"]
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as c:
                r = await c.get(f"{DATA_URL}/trades", params={"maker": address, "limit": 10})
                r.raise_for_status()
                data = r.json()

            trades = data if isinstance(data, list) else data.get("history", data.get("trades", []))
            if not isinstance(trades, list):
                return

        except Exception:
            return

        # Build trade ID set — use id, transactionHash, or a composite key
        def trade_id(t: dict) -> str:
            return str(
                t.get("id")
                or t.get("transactionHash")
                or f"{t.get('market','')}-{t.get('timestamp','')}-{t.get('price','')}"
            )

        known_ids = await rc.get_wallet_trade_ids(address)
        current_ids = {trade_id(t) for t in trades}
        new_trades = [t for t in trades if trade_id(t) not in known_ids]

        # Save baseline on first poll — don't emit signals for historical trades
        if not known_ids:
            await rc.set_wallet_trade_ids(address, current_ids)
            return

        await rc.set_wallet_trade_ids(address, current_ids)

        for trade in new_trades:
            await self._process_new_trade(wallet, trade)

    # ─── Signal Generation ────────────────────────────────────────────────────

    async def _process_new_trade(self, wallet: dict, trade: dict):
        market_id = str(
            trade.get("conditionId")
            or trade.get("market")
            or trade.get("market_id")
            or ""
        )
        if not market_id:
            return

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

        signal = {
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

        await rc.push_wallet_signal(signal)

        log_msg = (
            f"[WALLET] {signal_type} market={market_id[:24]} "
            f"wallets={wallet_count} confidence={confidence}"
        )
        await self._log("INFO", log_msg)
        print(f"[WALLET TRACKER] {log_msg} direction={direction} price={price}")

        try:
            msg = WSMessage(type="wallet_signal", payload=signal)
            await self.broadcast(msg.model_dump())
        except Exception:
            pass

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
