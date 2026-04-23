import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    polymarket_private_key: str = ""
    wallet_address: str = "0xeB5df547a289f98C39C136EA52fB94F11c5e92Ad"

    redis_url: str = "redis://redis:6379"

    paper_trading: bool = True
    max_position_size_usd: float = 100.0
    session_bankroll_usd: float = 1000.0

    scan_interval_seconds: int = 30
    max_opportunities_per_scan: int = 12
    min_liquidity_usd: float = 5000.0
    min_anomaly_score: float = 65.0
    min_conviction: float = 65.0

    claude_model: str = "claude-sonnet-4-20250514"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
