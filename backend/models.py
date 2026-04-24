from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime
import uuid


# ─── Polymarket Market ────────────────────────────────────────────────────────

class MarketToken(BaseModel):
    token_id: str
    outcome: str
    price: float = 0.0


class Market(BaseModel):
    id: str
    question: str
    condition_id: str = ""
    slug: str = ""
    category: str = ""
    volume: float = 0.0
    volume_24h: float = 0.0
    liquidity: float = 0.0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    tokens: List[MarketToken] = []
    active: bool = True
    closed: bool = False
    description: str = ""


# ─── Scanner Output ───────────────────────────────────────────────────────────

class MarketOpportunity(BaseModel):
    market_id: str
    question: str
    current_price: float
    implied_probability: float
    volume_24h: float
    liquidity: float
    anomaly_score: float = 50.0
    anomaly_type: Literal["price_drift", "volume_spike", "liquidity_gap", "correlation_divergence"] = "price_drift"
    time_to_resolution: str
    resolution_criteria: str
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    reason: str


class MarketState(BaseModel):
    total_volume_session: float
    avg_liquidity: float
    dominant_category: str
    session_bias: Literal["RISK_ON", "RISK_OFF", "NEUTRAL"] = "NEUTRAL"

    @field_validator("session_bias", mode="before")
    @classmethod
    def normalize_session_bias(cls, v):
        if isinstance(v, str) and v.upper() in ("RISK_ON", "RISK_OFF", "NEUTRAL"):
            return v.upper()
        return "NEUTRAL"


class ScannerOutput(BaseModel):
    scan_timestamp: str
    markets_scanned: int
    opportunities: List[MarketOpportunity]
    market_state: MarketState


# ─── Signal Output ────────────────────────────────────────────────────────────

class Evidence(BaseModel):
    source: str
    content: str
    weight: Literal["STRONG", "MODERATE", "WEAK"]
    direction: Literal["SUPPORTS", "CONTRADICTS"]


class SignalOutput(BaseModel):
    market_id: str
    thesis: str = ""
    direction: Literal["YES", "NO"] = "NO"
    true_probability: float = 0.0
    market_probability: float = 0.0
    edge: float = 0.0
    conviction: float = 0.0
    evidence: List[Evidence] = []
    base_rate: str = ""
    invalidation: str = ""
    time_sensitivity: Literal["IMMEDIATE", "HOURS", "DAYS"] = "DAYS"
    recommendation: Literal["TRADE", "MONITOR", "PASS", "VETO"] = "PASS"
    reasoning: str = ""

    @field_validator("direction", mode="before")
    @classmethod
    def normalize_direction(cls, v):
        if isinstance(v, str) and v.upper() in ("YES", "NO"):
            return v.upper()
        return "YES"

    @field_validator("true_probability", "market_probability", "edge", "conviction", mode="before")
    @classmethod
    def coerce_float(cls, v):
        if v is None:
            return 0.0
        return float(v)


# ─── Risk Output ──────────────────────────────────────────────────────────────

class RiskOutput(BaseModel):
    market_id: str
    decision: Literal["APPROVED", "RESIZED", "VETOED"]
    original_size: float
    approved_size: float
    kelly_fraction: float
    portfolio_concentration_after: float
    correlation_risk: Literal["LOW", "MEDIUM", "HIGH"]
    veto_reason: Optional[str] = None
    resize_reason: Optional[str] = None
    risk_delta: Literal["COOLING", "NEUTRAL", "HEATING"]
    session_health: Literal["GREEN", "YELLOW", "RED"]
    notes: str


# ─── Execution Output ─────────────────────────────────────────────────────────

class Tranche(BaseModel):
    size: float
    price_limit: float
    sequence: int


class EntryPlan(BaseModel):
    total_size: float
    tranches: List[Tranche]
    expected_avg_price: float
    estimated_impact: float


class ExitPlan(BaseModel):
    reason: Optional[Literal["THESIS_INVALID", "TARGET_REACHED", "TIME_STOP"]] = None
    size_to_exit: float
    urgency: Literal["IMMEDIATE", "NORMAL", "OPPORTUNISTIC"]


class PositionHealth(BaseModel):
    thesis_valid: bool
    invalidation_risk: Literal["LOW", "MEDIUM", "HIGH", "TRIGGERED"]
    time_remaining: str
    recommended_action: Literal["HOLD", "SCALE_OUT", "EXIT", "ADD"]


class ExecutionOutput(BaseModel):
    action: Literal["ENTER", "EXIT", "MONITOR", "ALERT"]
    market_id: str
    entry: Optional[EntryPlan] = None
    exit: Optional[ExitPlan] = None
    position_health: Optional[PositionHealth] = None
    notes: str


# ─── Position & Trade ─────────────────────────────────────────────────────────

class Position(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    market_id: str
    question: str
    direction: Literal["YES", "NO"]
    size_usd: float
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    status: Literal["OPEN", "CLOSED", "PARTIAL"] = "OPEN"
    opened_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    closed_at: Optional[str] = None
    thesis: str = ""
    invalidation: str = ""


class Trade(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    market_id: str
    question: str
    direction: Literal["YES", "NO"]
    size_usd: float
    price: float
    side: Literal["BUY", "SELL"]
    status: Literal["FILLED", "PARTIAL", "CANCELLED", "PENDING"] = "PENDING"
    paper: bool = True
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    order_id: Optional[str] = None


# ─── Portfolio State ──────────────────────────────────────────────────────────

class PortfolioState(BaseModel):
    bankroll: float
    deployed: float
    available: float
    session_pnl: float
    total_pnl: float
    win_rate: float
    avg_profit: float
    total_trades: int
    winning_trades: int
    open_positions: int
    session_drawdown: float
    session_health: Literal["GREEN", "YELLOW", "RED"] = "GREEN"


# ─── Agent Log Entry ──────────────────────────────────────────────────────────

class AgentLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    agent: Literal["SCANNER", "SIGNAL", "RISK", "EXECUTION", "SYSTEM"]
    level: Literal["INFO", "WARN", "ERROR", "TRADE", "VETO"] = "INFO"
    message: str
    data: Optional[dict] = None


# ─── WebSocket Messages ───────────────────────────────────────────────────────

class WSMessage(BaseModel):
    type: str
    payload: dict
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
