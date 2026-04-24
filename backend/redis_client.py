import json
import redis.asyncio as aioredis
from datetime import datetime
from typing import Optional, Any
from config import settings
from models import (
    AgentLogEntry, Position, Trade, PortfolioState,
    ScannerOutput, SignalOutput, RiskOutput, ExecutionOutput
)

redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global redis
    if redis is None:
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return redis


async def ping() -> bool:
    try:
        r = await get_redis()
        await r.ping()
        return True
    except Exception:
        return False


# ─── Agent Log ────────────────────────────────────────────────────────────────

async def log_agent_event(entry: AgentLogEntry):
    r = await get_redis()
    key = "sigforge:log"
    await r.lpush(key, entry.model_dump_json())
    await r.ltrim(key, 0, 999)  # keep last 1000 entries


async def get_agent_log(limit: int = 100) -> list[dict]:
    r = await get_redis()
    entries = await r.lrange("sigforge:log", 0, limit - 1)
    return [json.loads(e) for e in entries]


# ─── Agent State ──────────────────────────────────────────────────────────────

async def save_agent_output(agent: str, data: dict):
    r = await get_redis()
    key = f"sigforge:agent:{agent.lower()}:last"
    payload = {"timestamp": datetime.utcnow().isoformat(), "data": data}
    await r.set(key, json.dumps(payload), ex=3600)


async def get_agent_output(agent: str) -> Optional[dict]:
    r = await get_redis()
    key = f"sigforge:agent:{agent.lower()}:last"
    val = await r.get(key)
    return json.loads(val) if val else None


# ─── Portfolio State ──────────────────────────────────────────────────────────

async def save_portfolio(state: PortfolioState):
    r = await get_redis()
    await r.set("sigforge:portfolio", state.model_dump_json(), ex=3600)


async def get_portfolio() -> Optional[PortfolioState]:
    r = await get_redis()
    val = await r.get("sigforge:portfolio")
    return PortfolioState.model_validate_json(val) if val else None


async def init_portfolio() -> PortfolioState:
    state = PortfolioState(
        bankroll=settings.session_bankroll_usd,
        deployed=0.0,
        available=settings.session_bankroll_usd,
        session_pnl=0.0,
        total_pnl=0.0,
        win_rate=0.0,
        avg_profit=0.0,
        total_trades=0,
        winning_trades=0,
        open_positions=0,
        session_drawdown=0.0,
        session_health="GREEN",
    )
    await save_portfolio(state)
    return state


# ─── Positions ────────────────────────────────────────────────────────────────

async def save_position(pos: Position):
    r = await get_redis()
    await r.hset("sigforge:positions", pos.id, pos.model_dump_json())


async def get_positions() -> list[Position]:
    r = await get_redis()
    raw = await r.hgetall("sigforge:positions")
    return [Position.model_validate_json(v) for v in raw.values()]


async def get_open_positions() -> list[Position]:
    positions = await get_positions()
    return [p for p in positions if p.status == "OPEN"]


async def update_position(pos: Position):
    await save_position(pos)


# ─── Trades ───────────────────────────────────────────────────────────────────

async def save_trade(trade: Trade):
    r = await get_redis()
    await r.lpush("sigforge:trades", trade.model_dump_json())
    await r.ltrim("sigforge:trades", 0, 499)


async def get_trades(limit: int = 50) -> list[Trade]:
    r = await get_redis()
    raw = await r.lrange("sigforge:trades", 0, limit - 1)
    return [Trade.model_validate_json(t) for t in raw]


# ─── Session P&L History ──────────────────────────────────────────────────────

async def record_pnl_snapshot(pnl: float):
    r = await get_redis()
    snapshot = json.dumps({
        "timestamp": datetime.utcnow().isoformat(),
        "pnl": pnl
    })
    await r.lpush("sigforge:pnl_history", snapshot)
    await r.ltrim("sigforge:pnl_history", 0, 2879)  # ~24h at 30s intervals


async def get_pnl_history(limit: int = 100) -> list[dict]:
    r = await get_redis()
    raw = await r.lrange("sigforge:pnl_history", 0, limit - 1)
    result = [json.loads(x) for x in raw]
    return list(reversed(result))  # oldest first


# ─── Signal History ───────────────────────────────────────────────────────────

async def save_signal(signal: dict):
    r = await get_redis()
    payload = json.dumps({"timestamp": datetime.utcnow().isoformat(), **signal})
    await r.lpush("sigforge:signals", payload)
    await r.ltrim("sigforge:signals", 0, 199)


async def get_signals(limit: int = 50) -> list[dict]:
    r = await get_redis()
    raw = await r.lrange("sigforge:signals", 0, limit - 1)
    return [json.loads(x) for x in raw]


# ─── Scanner State ────────────────────────────────────────────────────────────

async def save_scan_result(result: dict):
    r = await get_redis()
    await r.set("sigforge:last_scan", json.dumps(result), ex=120)
    await r.lpush("sigforge:scan_history", json.dumps({
        "timestamp": datetime.utcnow().isoformat(),
        "markets_scanned": result.get("markets_scanned", 0),
        "opportunities_found": len(result.get("opportunities", []))
    }))
    await r.ltrim("sigforge:scan_history", 0, 99)


async def get_last_scan() -> Optional[dict]:
    r = await get_redis()
    val = await r.get("sigforge:last_scan")
    return json.loads(val) if val else None


# ─── Wallet Tracker ──────────────────────────────────────────────────────────

async def set_smart_wallets(wallets: list[dict]):
    r = await get_redis()
    await r.set("sigforge:wallets:smart_list", json.dumps(wallets), ex=7200)


async def get_smart_wallets() -> list[dict]:
    r = await get_redis()
    val = await r.get("sigforge:wallets:smart_list")
    return json.loads(val) if val else []


async def get_wallet_trade_ids(address: str) -> set[str]:
    r = await get_redis()
    val = await r.get(f"sigforge:wallets:trades:{address.lower()}")
    return set(json.loads(val)) if val else set()


async def set_wallet_trade_ids(address: str, ids: set[str]):
    r = await get_redis()
    await r.set(
        f"sigforge:wallets:trades:{address.lower()}",
        json.dumps(list(ids)),
        ex=3600,
    )


async def push_wallet_signal(signal: dict):
    r = await get_redis()
    await r.lpush("sigforge:wallets:queue", json.dumps(signal))
    await r.ltrim("sigforge:wallets:queue", 0, 99)


async def get_queued_wallet_market_ids() -> set[str]:
    """Return the set of market_ids currently sitting in the wallet signal queue."""
    r = await get_redis()
    raw = await r.lrange("sigforge:wallets:queue", 0, -1)
    ids = set()
    for item in raw:
        try:
            ids.add(json.loads(item).get("market_id", ""))
        except Exception:
            pass
    ids.discard("")
    return ids


async def drain_wallet_signals() -> list[dict]:
    """Pop all pending wallet signals from queue (FIFO)."""
    r = await get_redis()
    signals = []
    while True:
        val = await r.rpop("sigforge:wallets:queue")
        if val is None:
            break
        try:
            signals.append(json.loads(val))
        except Exception:
            pass
    return signals


# ─── Session Stats ────────────────────────────────────────────────────────────

async def increment_stat(key: str, amount: float = 1.0):
    r = await get_redis()
    await r.incrbyfloat(f"sigforge:stats:{key}", amount)


async def get_stat(key: str) -> float:
    r = await get_redis()
    val = await r.get(f"sigforge:stats:{key}")
    return float(val) if val else 0.0


async def get_all_stats() -> dict:
    keys = ["total_scans", "total_signals", "total_trades", "total_vetoes",
            "consecutive_losses", "session_wins", "session_losses"]
    r = await get_redis()
    result = {}
    for k in keys:
        val = await r.get(f"sigforge:stats:{k}")
        result[k] = float(val) if val else 0.0
    return result
