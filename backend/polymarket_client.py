"""
Polymarket API Client
Covers: Gamma API, Data API, CLOB API (public + authenticated)
WebSocket: live price subscriptions
"""
import asyncio
import json
import os
import time
from typing import Optional, Callable, Awaitable
from datetime import datetime, timezone

import httpx
import websockets
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings

# ─── Base URLs ────────────────────────────────────────────────────────────────

GAMMA_URL = "https://gamma-api.polymarket.com"
DATA_URL = "https://data-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
CLOB_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


# ─── HTTP Client ─────────────────────────────────────────────────────────────

def _make_client(base_url: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(15.0),
        headers={"User-Agent": "SigForge/1.0"},
        follow_redirects=True,
    )


# ─── Gamma API ───────────────────────────────────────────────────────────────

class GammaClient:
    """Public market metadata — no auth required."""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
        active: bool = True,
    ) -> list[dict]:
        params = {"limit": limit, "offset": offset, "active": str(active).lower()}
        if search:
            params["search"] = search
        async with _make_client(GAMMA_URL) as c:
            r = await c.get("/markets", params=params)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else data.get("markets", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_events(self, limit: int = 50) -> list[dict]:
        async with _make_client(GAMMA_URL) as c:
            r = await c.get("/events", params={"limit": limit})
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else data.get("events", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_top_markets(self, limit: int = 50) -> list[dict]:
        """Fetch top markets sorted by volume."""
        params = {
            "limit": limit,
            "active": "true",
            "_sort": "volume",
            "_order": "DESC",
        }
        async with _make_client(GAMMA_URL) as c:
            r = await c.get("/markets", params=params)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else data.get("markets", [])


# ─── Data API ─────────────────────────────────────────────────────────────────

class DataClient:
    """User portfolio data — no auth required."""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_positions(self, address: str) -> list[dict]:
        async with _make_client(DATA_URL) as c:
            r = await c.get("/positions", params={"user": address})
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else data.get("positions", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_trades(self, address: str, limit: int = 50) -> list[dict]:
        async with _make_client(DATA_URL) as c:
            r = await c.get("/trades", params={"user": address, "limit": limit})
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else data.get("history", [])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_portfolio_value(self, address: str) -> dict:
        async with _make_client(DATA_URL) as c:
            r = await c.get("/value", params={"user": address})
            r.raise_for_status()
            return r.json()


# ─── CLOB API (public) ────────────────────────────────────────────────────────

class ClobClient:
    """CLOB API — public endpoints (prices, orderbook, markets)."""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_markets(self, next_cursor: str = "") -> dict:
        params = {}
        if next_cursor:
            params["next_cursor"] = next_cursor
        async with _make_client(CLOB_URL) as c:
            r = await c.get("/markets", params=params)
            r.raise_for_status()
            return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_orderbook(self, token_id: str) -> dict:
        async with _make_client(CLOB_URL) as c:
            r = await c.get("/book", params={"token_id": token_id})
            r.raise_for_status()
            return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_price(self, token_id: str, side: str = "BUY") -> float:
        async with _make_client(CLOB_URL) as c:
            r = await c.get("/price", params={"token_id": token_id, "side": side})
            r.raise_for_status()
            data = r.json()
            return float(data.get("price", 0))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_midpoint(self, token_id: str) -> float:
        async with _make_client(CLOB_URL) as c:
            r = await c.get("/midpoint", params={"token_id": token_id})
            r.raise_for_status()
            data = r.json()
            return float(data.get("mid", 0))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_spread(self, token_id: str) -> dict:
        async with _make_client(CLOB_URL) as c:
            r = await c.get("/spread", params={"token_id": token_id})
            r.raise_for_status()
            return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_all_markets_paginated(self, max_pages: int = 5) -> list[dict]:
        """Fetch multiple pages of CLOB markets."""
        all_markets = []
        cursor = ""
        for _ in range(max_pages):
            data = await self.get_markets(next_cursor=cursor)
            markets = data.get("data", [])
            all_markets.extend(markets)
            next_cursor = data.get("next_cursor", "")
            if not next_cursor or next_cursor == "LTE=":
                break
            cursor = next_cursor
        return all_markets


# ─── Authenticated CLOB Client ────────────────────────────────────────────────

class AuthenticatedClobClient:
    """
    Authenticated operations using py-clob-client.
    Only used when PAPER_TRADING=false.
    Private key is never logged — loaded from env only.
    """

    def __init__(self):
        self._client = None
        self._initialized = False

    def _get_client(self):
        if self._initialized:
            return self._client
        private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
        if not private_key:
            raise ValueError("POLYMARKET_PRIVATE_KEY not set — cannot use authenticated CLOB")
        try:
            from py_clob_client.client import ClobClient as PyClobClient
            from py_clob_client.clob_types import ApiCreds

            self._client = PyClobClient(
                host=CLOB_URL,
                key=private_key,
                chain_id=137,  # Polygon
            )
            self._initialized = True
            return self._client
        except Exception as e:
            raise RuntimeError(f"Failed to init py-clob-client: {e}")

    async def place_order(
        self,
        token_id: str,
        side: str,
        size: float,
        price: float,
    ) -> dict:
        if settings.paper_trading:
            return {
                "paper": True,
                "order_id": f"PAPER-{int(time.time())}",
                "token_id": token_id,
                "side": side,
                "size": size,
                "price": price,
                "status": "FILLED",
            }
        client = self._get_client()
        from py_clob_client.clob_types import OrderArgs, OrderType
        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=side,
        )
        result = client.create_and_post_order(order_args)
        return result

    async def cancel_order(self, order_id: str) -> dict:
        if settings.paper_trading:
            return {"paper": True, "cancelled": order_id}
        client = self._get_client()
        return client.cancel(order_id=order_id)

    async def get_orders(self) -> list[dict]:
        if settings.paper_trading:
            return []
        client = self._get_client()
        return client.get_orders()


# ─── WebSocket Live Price Feed ────────────────────────────────────────────────

class PolymarketWebSocket:
    """
    Subscribe to live price updates from Polymarket CLOB WebSocket.
    Reconnects automatically on disconnect.
    """

    def __init__(self, on_message: Callable[[dict], Awaitable[None]]):
        self.on_message = on_message
        self._running = False
        self._subscribed_markets: list[str] = []
        self._ws = None

    async def subscribe(self, market_ids: list[str]):
        self._subscribed_markets = market_ids

    async def run(self):
        self._running = True
        while self._running:
            try:
                await self._connect_and_stream()
            except Exception as e:
                if self._running:
                    await asyncio.sleep(5)

    async def _connect_and_stream(self):
        async with websockets.connect(
            CLOB_WS_URL,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            self._ws = ws
            # Subscribe to markets if any
            if self._subscribed_markets:
                sub_msg = {
                    "type": "subscribe",
                    "channel": "market",
                    "market_ids": self._subscribed_markets,
                }
                await ws.send(json.dumps(sub_msg))

            async for raw in ws:
                try:
                    data = json.loads(raw)
                    await self.on_message(data)
                except json.JSONDecodeError:
                    pass

    def stop(self):
        self._running = False


# ─── Composite Polymarket Client ──────────────────────────────────────────────

class PolymarketClient:
    """Unified access to all Polymarket APIs."""

    def __init__(self):
        self.gamma = GammaClient()
        self.data = DataClient()
        self.clob = ClobClient()
        self.auth = AuthenticatedClobClient()

    async def get_top_markets_enriched(self, limit: int = 50) -> list[dict]:
        """
        Fetch top markets from Gamma and enrich with CLOB price data.
        Returns list of dicts with merged metadata + pricing.
        """
        gamma_markets = await self.gamma.get_top_markets(limit=limit)

        result = []
        for m in gamma_markets:
            try:
                tokens = m.get("tokens", [])
                enriched = {
                    "id": m.get("id", ""),
                    "question": m.get("question", ""),
                    "condition_id": m.get("conditionId", ""),
                    "slug": m.get("slug", ""),
                    "category": _extract_category(m),
                    "volume": float(m.get("volume", 0) or 0),
                    "volume_24h": float(m.get("volume24hr", 0) or 0),
                    "liquidity": float(m.get("liquidity", 0) or 0),
                    "start_date": m.get("startDate"),
                    "end_date": m.get("endDate"),
                    "active": m.get("active", True),
                    "closed": m.get("closed", False),
                    "description": m.get("description", ""),
                    "tokens": [
                        {
                            "token_id": t.get("token_id", ""),
                            "outcome": t.get("outcome", ""),
                            "price": float(t.get("price", 0) or 0),
                        }
                        for t in tokens
                    ],
                }
                result.append(enriched)
            except Exception:
                continue

        return result

    async def get_wallet_portfolio(self) -> dict:
        """Fetch live portfolio data for the configured wallet."""
        address = settings.wallet_address
        positions = await self.data.get_positions(address)
        trades = await self.data.get_trades(address, limit=20)
        try:
            value = await self.data.get_portfolio_value(address)
        except Exception:
            value = {}
        return {
            "address": address,
            "positions": positions,
            "recent_trades": trades,
            "portfolio_value": value,
        }


def _extract_category(market: dict) -> str:
    tags = market.get("tags", [])
    if tags:
        if isinstance(tags[0], str):
            return tags[0]
        if isinstance(tags[0], dict):
            return tags[0].get("label", "")
    cat = market.get("category", "")
    return cat if cat else "general"


# ─── Singleton ────────────────────────────────────────────────────────────────

polymarket = PolymarketClient()
