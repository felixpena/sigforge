# SIG//FORGE

4-agent autonomous trading system for Polymarket.

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY and POLYMARKET_PRIVATE_KEY

# 2. Launch full stack
docker-compose up

# Dashboard → http://localhost:3000
# API       → http://localhost:8000
# Health    → http://localhost:8000/health
```

## Architecture

```
POLYMARKET MARKETS
       ↓
  [ SCANNER ]  — finds anomalies (Claude)
       ↓
  [ SIGNAL ]   — researches edge (Claude)
       ↓
  [ RISK ]     — Kelly sizing + vetoes (Claude)
       ↓
  [ EXECUTION ]— order management (Claude)
       ↓
  Redis ← state → FastAPI → WebSocket → React Dashboard
```

## Agents

| Agent | Role | Output |
|-------|------|--------|
| SCANNER | Market anomaly detection | Opportunities ranked by anomaly score |
| SIGNAL | Research & conviction scoring | Trade recommendation + evidence |
| RISK | Kelly sizing + veto conditions | Approved size or veto |
| EXECUTION | Order structuring & monitoring | Entry/exit tranches |

## Safety

- **PAPER_TRADING=true** by default — no real capital at risk
- Private key loaded from env only — never logged
- Session drawdown >20% → all new positions blocked (RED health)
- Conviction <65 → automatic veto
- Kelly capped at 25%

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | required |
| `POLYMARKET_PRIVATE_KEY` | Wallet private key | required for live |
| `PAPER_TRADING` | Paper mode flag | `true` |
| `SESSION_BANKROLL_USD` | Starting bankroll | `1000` |
| `MAX_POSITION_SIZE_USD` | Max single position | `100` |
| `SCAN_INTERVAL_SECONDS` | Scan frequency | `30` |

## Dev (without Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Redis
docker run -p 6379:6379 redis:7-alpine

# Integration test
cd backend
python test_integration.py
```
