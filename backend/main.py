"""
SIG//FORGE — FastAPI Backend
WebSocket streams agent activity to frontend in real-time.
REST endpoints for portfolio, trades, positions, history.
"""
import asyncio
import json
from typing import Set
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from orchestrator import Orchestrator
from models import WSMessage
from config import settings
import redis_client as rc
from polymarket_client import polymarket

# ─── WebSocket Connection Manager ────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active.discard(ws)


manager = ConnectionManager()
orchestrator: Orchestrator = None
orch_task: asyncio.Task = None


# ─── App Lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator, orch_task

    # Verify Redis connection
    redis_ok = await rc.ping()
    if redis_ok:
        print("[SIGFORGE] Redis connected")
    else:
        print("[SIGFORGE] WARNING: Redis not available")

    # Initialize portfolio
    portfolio = await rc.get_portfolio()
    if not portfolio:
        await rc.init_portfolio()

    # Start orchestrator in background
    orchestrator = Orchestrator(broadcast=manager.broadcast)
    if settings.anthropic_api_key:
        orch_task = asyncio.create_task(orchestrator.start())
        print("[SIGFORGE] Orchestrator started")
    else:
        print("[SIGFORGE] WARNING: ANTHROPIC_API_KEY not set — orchestrator paused")

    yield

    # Shutdown
    if orch_task:
        orchestrator.stop()
        orch_task.cancel()
        try:
            await orch_task
        except asyncio.CancelledError:
            pass
    print("[SIGFORGE] Shutdown complete")


app = FastAPI(
    title="SIG//FORGE",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    redis_ok = await rc.ping()
    return {
        "status": "ok",
        "redis": redis_ok,
        "paper_trading": settings.paper_trading,
        "anthropic_configured": bool(settings.anthropic_api_key),
        "orchestrator_running": orch_task is not None and not orch_task.done(),
    }


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Send initial state on connect
        portfolio = await rc.get_portfolio()
        if portfolio:
            await ws.send_json(WSMessage(type="portfolio", payload=portfolio.model_dump()).model_dump())

        log_entries = await rc.get_agent_log(limit=50)
        await ws.send_json(WSMessage(type="log_history", payload={"entries": log_entries}).model_dump())

        trades = await rc.get_trades(limit=20)
        await ws.send_json(WSMessage(type="trade_history", payload={"trades": [t.model_dump() for t in trades]}).model_dump())

        pnl_history = await rc.get_pnl_history(limit=100)
        await ws.send_json(WSMessage(type="pnl_history", payload={"history": pnl_history}).model_dump())

        positions = await rc.get_open_positions()
        await ws.send_json(WSMessage(type="positions", payload={"positions": [p.model_dump() for p in positions]}).model_dump())

        last_scan = await rc.get_last_scan()
        if last_scan:
            await ws.send_json(WSMessage(type="scan_complete", payload=last_scan).model_dump())

        # ── Server-side ping task — fires every 15s ──────────────────
        async def heartbeat():
            while True:
                await asyncio.sleep(15)
                try:
                    await ws.send_json({
                        "type": "heartbeat",
                        "payload": {},
                        "timestamp": asyncio.get_event_loop().time().__str__(),
                    })
                except Exception:
                    break  # socket is dead — let receive loop detect it

        # ── Receive loop — client pings answered, disconnects detected ─
        async def receive():
            while True:
                try:
                    # Wait up to 60s for any client message before giving up
                    data = await asyncio.wait_for(ws.receive_text(), timeout=60)
                    if data == "ping":
                        await ws.send_text("pong")
                except asyncio.TimeoutError:
                    # No message in 60s — send an extra server ping
                    try:
                        await ws.send_json({"type": "heartbeat", "payload": {}, "timestamp": ""})
                    except Exception:
                        break
                except WebSocketDisconnect:
                    break
                except Exception:
                    break

        # Run both tasks concurrently; cancel the other when one exits
        heartbeat_task = asyncio.create_task(heartbeat())
        receive_task = asyncio.create_task(receive())
        try:
            done, pending = await asyncio.wait(
                {heartbeat_task, receive_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (heartbeat_task, receive_task):
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)


# ─── REST Endpoints ───────────────────────────────────────────────────────────

@app.get("/api/portfolio")
async def get_portfolio():
    portfolio = await rc.get_portfolio()
    return portfolio.model_dump() if portfolio else {}


@app.get("/api/positions")
async def get_positions():
    positions = await rc.get_open_positions()
    return {"positions": [p.model_dump() for p in positions]}


@app.get("/api/trades")
async def get_trades(limit: int = 50):
    trades = await rc.get_trades(limit=limit)
    return {"trades": [t.model_dump() for t in trades]}


@app.get("/api/log")
async def get_log(limit: int = 100):
    entries = await rc.get_agent_log(limit=limit)
    return {"entries": entries}


@app.get("/api/pnl-history")
async def get_pnl_history(limit: int = 200):
    history = await rc.get_pnl_history(limit=limit)
    return {"history": history}


@app.get("/api/signals")
async def get_signals(limit: int = 50):
    signals = await rc.get_signals(limit=limit)
    return {"signals": signals}


@app.get("/api/last-scan")
async def get_last_scan():
    scan = await rc.get_last_scan()
    return scan or {}


@app.get("/api/stats")
async def get_stats():
    stats = await rc.get_all_stats()
    portfolio = await rc.get_portfolio()
    return {
        "stats": stats,
        "portfolio": portfolio.model_dump() if portfolio else {},
        "paper_trading": settings.paper_trading,
    }


@app.get("/api/markets")
async def get_markets(limit: int = 20):
    """Fetch top markets for display."""
    try:
        markets = await polymarket.get_top_markets_enriched(limit=limit)
        return {"markets": markets[:limit]}
    except Exception as e:
        return {"markets": [], "error": str(e)}


@app.get("/api/agent/{agent_name}")
async def get_agent_state(agent_name: str):
    output = await rc.get_agent_output(agent_name)
    return output or {"error": "no data"}


@app.post("/api/orchestrator/restart")
async def restart_orchestrator():
    global orchestrator, orch_task
    if orch_task and not orch_task.done():
        orchestrator.stop()
        orch_task.cancel()
        try:
            await orch_task
        except asyncio.CancelledError:
            pass

    if settings.anthropic_api_key:
        orchestrator = Orchestrator(broadcast=manager.broadcast)
        orch_task = asyncio.create_task(orchestrator.start())
        return {"status": "restarted"}
    return {"status": "error", "message": "ANTHROPIC_API_KEY not configured"}
