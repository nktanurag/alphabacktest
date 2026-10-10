# AlphaBacktest backend

Python service that runs a historical backtest for a user-defined trading strategy and returns performance metrics plus every simulated trade.

## Layout

```
backend/
├── requirements.txt        # dependencies
├── requirements.txt        # runtime deps
├── requirements-dev.txt    # test-only deps (`ta`, used to cross-check indicators)
├── alphabacktest/
│   ├── models.py           # request/response shapes (Pydantic)
│   ├── db.py / orm.py      # SQLAlchemy engine/session and tables (users, strategies)
│   ├── strategies.py       # saved-strategy CRUD endpoints
│   ├── data.py             # downloads historical prices (yfinance)
│   ├── indicators.py       # SMA, EMA, RSI, Bollinger, MACD, volume
│   ├── engine.py           # the backtest simulation + metrics
│   └── api.py              # FastAPI endpoints
└── tests/test_engine.py    # unit tests for indicators and engine
```

## Request flow

`POST /api/backtest` with a strategy JSON:

1. **api.py** — FastAPI parses the body into a `Strategy` (`models.py`). Malformed input is rejected automatically; business rules (`validate_strategy`) return 400.
2. **data.py** — `fetch_daily_bars` downloads daily OHLCV from Yahoo Finance, starting 400 calendar days before `startDate` (so long indicators like SMA(200) are ready on day one) and 60 days past `endDate` (so late trades can still exit). Prices are split/dividend adjusted. Results are cached for 6 hours. Failure returns 502.
3. **engine.py** — `run_backtest` walks the bars one by one (see below). Failure returns 422.
4. **api.py** — returns a `BacktestResult`: metrics, trades, warnings.

## How the engine decides

- Each condition is `left (indicator) <operator> right (indicator or fixed number)`, e.g. `RSI(14) less_than 30` or `SMA(7) crosses_above SMA(14)`.
- **All entry conditions must be true at once (AND).**
- Rules: long-only, one position at a time.
- Exit rules are checked bar by bar and the first to trigger wins: a signal exit flagged the previous day (next_open mode), then stop-loss, then take-profit (both use the day's low/high; a gap through the level fills at the open; if one day could hit both, the stop-loss is assumed first), then the holding period, then the end of the date range, then a signal exit on this bar's close.
- By default a signal on a bar's close **enters at the next bar's open** (avoids look-ahead bias); `entryTiming: signal_close` enters at that same close instead. The position **exits at the close `exitDays` trading days after entry**; if the date range ends first, it is closed on the last day in range.
- Slippage worsens both fills; commission is charged on both sides.
- Position size is a percentage of current cash.
- Signals are only taken between `startDate` and `endDate`; earlier bars are indicator warm-up only.
- Each trade stores `entryReasons` (which conditions fired) and `exitReason`, for the "why did this trigger?" view.
- Metrics (total return, CAGR, win rate, profit factor, max drawdown, Sharpe) come from daily mark-to-market equity.

## Files in detail

| File | Role |
|---|---|
| `models.py` | `Strategy`, `Condition`, `Indicator`/`Value` operands, `Trade`, `BacktestResult`. This is the JSON contract with the UI. |
| `indicators.py` | Pure functions over pandas Series. `compute_series` maps an indicator spec to numbers. `Volume(20)` means 20-bar average volume. |
| `engine.py` | `validate_strategy`, condition evaluation (including crossovers), the bar-by-bar loop, and `_summarize` for metrics. |
| `data.py` | Only place that talks to the market data provider; swap it to change data source. |
| `api.py` | HTTP layer only; no business logic. |

## Run

Requires Python 3.10+. Full setup (including the frontend) is in the [root README](../README.md).

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn alphabacktest.api:app --port 8080 --reload
pip install -r requirements-dev.txt && python -m pytest
```

Example:

```
curl -X POST localhost:8080/api/backtest -H 'content-type: application/json' -d '{
  "name": "t", "asset": "TSLA", "startDate": "2022-01-01", "endDate": "2024-12-31",
  "entryConditions": [{"id": "1", "left": {"name": "RSI", "period": 14},
                       "operator": "less_than", "right": {"kind": "value", "value": 35}}],
  "exitDays": 14, "initialCapital": 100000, "positionSizePct": 100,
  "commissionPct": 0.1, "slippagePct": 0.1}'
```

## API: `POST /api/backtest`

Synchronous: the response arrives when the run finishes (a few seconds, mostly the data download). Interactive docs are served at `/docs`.

### Request

```json
{
  "name": "TSLA Oversold Crossover",
  "asset": "TSLA",
  "startDate": "2022-01-01",
  "endDate": "2024-12-31",
  "entryConditions": [
    { "id": "1",
      "left":  { "name": "SMA", "period": 7 },
      "operator": "crosses_above",
      "right": { "kind": "indicator", "name": "SMA", "period": 14 } },
    { "id": "2",
      "left":  { "name": "RSI", "period": 14 },
      "operator": "less_than",
      "right": { "kind": "value", "value": 30 } },
    { "id": "3",
      "left":  { "name": "VOLUME" },
      "operator": "greater_than",
      "right": { "kind": "indicator", "name": "VOLUME", "period": 20 } }
  ],
  "exitDays": 14,
  "stopLossPct": 5,
  "takeProfitPct": 10,
  "exitConditions": [],
  "entryTiming": "next_open",
  "initialCapital": 100000,
  "positionSizePct": 100,
  "commissionPct": 0.1,
  "slippagePct": 0.1
}
```

| Field | Meaning |
|---|---|
| `entryConditions` | List of any length. All must be true at once (AND). |
| `left` | Always an indicator: `{ "name": ..., "period": ... }`. |
| `right` | Either an indicator (`"kind": "indicator"`) or a fixed number (`"kind": "value"`). |
| `name` | `SMA`, `EMA`, `RSI`, `BB_UPPER`, `BB_LOWER`, `MACD`, `MACD_SIGNAL`, `VOLUME`, `PRICE`. |
| `period` | Required for `SMA`, `EMA`, `RSI`, `BB_UPPER`, `BB_LOWER`. For `VOLUME`, a period means average volume over that many bars. |
| `operator` | `crosses_above`, `crosses_below`, `greater_than`, `less_than`, `equals`. |
| `exitDays` | Optional. Close after this many trading days in the trade. `null` = no time limit. |
| `stopLossPct` | Optional. Sell if price falls this percent below entry (`5` = 5%). |
| `takeProfitPct` | Optional. Sell if price rises this percent above entry. |
| `exitConditions` | Optional list, same format as `entryConditions`. Sell when ALL are true. |

At least one exit rule is required (`exitDays`, `stopLossPct`, `takeProfitPct`, or a non-empty `exitConditions`). The first one to trigger closes the trade.
| `entryTiming` | Optional. `next_open` (default): act at the next day's open. `signal_close`: act at the close of the signal day (slightly optimistic). Applies to entries and to signal exits. |
| `positionSizePct` | Percent of cash used per trade (above 0, up to 100). |
| `commissionPct`, `slippagePct` | Percentages, so `0.1` means 0.1%. Applied on both entry and exit. |

### Success response (200)

Values below are illustrative.

```json
{
  "strategy": { "...": "echo of the request" },
  "totalReturnPct": 23.39,
  "cagrPct": 7.2,
  "winRatePct": 61.54,
  "profitFactor": 1.62,
  "maxDrawdownPct": -12.48,
  "sharpeRatio": 1.32,
  "totalTrades": 13,
  "winningTrades": 8,
  "losingTrades": 5,
  "avgTradeReturnPct": 1.83,
  "avgWinReturnPct": 5.72,
  "avgLossReturnPct": -3.41,
  "trades": [
    { "id": 1,
      "entryDate": "2022-03-24", "entryPrice": 368.40,
      "exitDate": "2022-04-13",  "exitPrice": 385.60,
      "holdingDays": 14, "returnPct": 4.67, "pnl": 4670.0,
      "result": "WIN",
      "entryReasons": [
        "SMA(7) crosses above SMA(14) (crossed above)",
        "RSI(14) < 30 (was less than)",
        "Volume > Volume(20) (was greater than)"
      ],
      "exitReason": "14 trading days reached" }
  ],
  "buyHoldReturnPct": 18.4,
  "buyHoldMaxDrawdownPct": -21.7,
  "equityCurve": [{ "date": "2022-01-03", "value": 100000.0 }],
  "benchmarkCurve": [{ "date": "2022-01-03", "value": 100000.0 }],
  "warnings": [],
  "currency": "USD"
}
```

- `profitFactor` and `sharpeRatio` can be `null` (no losing trades, or flat equity).
- `totalTrades: 0` with an empty `trades` list is a normal success ("No trades generated").
- `warnings` holds messages such as "Historical data starts on ..., after the selected start date."
- `equityCurve` is the strategy's daily value; `benchmarkCurve` is buy-and-hold of the same asset over the same dates **before costs**. Both have one point per trading day in range (plus `buyHoldReturnPct` / `buyHoldMaxDrawdownPct`).
- `exitReason` is one of: `N trading days reached`, `Stop-loss hit (...)`, `Take-profit hit (...)`, `Exit signal: ...`, `Backtest period ended`.
- `currency` is the asset's trading currency (e.g. `INR` for `RELIANCE.NS`).
- A trade still open on `endDate` is closed at that day's close (`exitReason`: "Backtest period ended", plus a warning), so trades, equity and metrics always agree.
- `entryReasons` powers the "why did this trigger?" view for each trade.

### Errors

| Status | When | Body |
|---|---|---|
| 400 | A business rule fails (no conditions, start after end, period under 1, ...) | `{"error": "invalid_strategy", "issues": ["Add at least one entry condition."]}` |
| 422 | Malformed request (wrong type, missing field): FastAPI's own validation body. Also used for engine failures | `{"error": "backtest_failed", "message": "..."}` for engine failures |
| 502 | Market data could not be loaded | `{"error": "data_unavailable", "message": "Historical market data could not be loaded."}` |

Note: 422 currently carries two different body shapes (FastAPI validation vs `backtest_failed`).

### `GET /api/symbols/search?q=apple`

Returns up to 8 stocks/ETFs matching a ticker or company name: `[{"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "type": "EQUITY"}]`. An empty `q` returns `[]`. A Yahoo failure returns 502 `{"error": "search_unavailable", ...}`.

### Saved strategies

All scoped to the current user (no login yet: a single local user, see `strategies.current_user()`).

| Method | Path | Notes |
|---|---|---|
| GET | `/api/strategies` | List, most recently updated first |
| POST | `/api/strategies` | Body `{name, description?, definition: <Strategy>}`; 201. Duplicate name for the same user returns 409 `name_taken` |
| GET | `/api/strategies/{id}` | 404 if it doesn't exist or belongs to someone else |
| PUT | `/api/strategies/{id}` | Same body as POST |
| DELETE | `/api/strategies/{id}` | 204 |

Storage: SQLite file `alphabacktest.db` in the working directory by default; set `DATABASE_URL` (e.g. `postgresql+psycopg://...`) for Postgres. Tables are created at startup. Tables: `users` (email, name, password_hash, auth_provider, auth_provider_id: reserved for login) and `strategies` (user_id, name, description, JSON `definition`).

### Health check

`GET /api/health` returns `{"ok": true}`.

## Not built yet

Login, export, OR logic, parameter optimization, stored backtest runs, database migrations (tables are auto-created).
