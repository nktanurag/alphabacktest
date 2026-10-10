# AlphaBacktest

A no-code historical strategy backtester. Pick a stock, define entry conditions (any number, combined with AND) and exit rules (holding period, stop-loss, take-profit, exit signal), and see how the strategy would have performed: metrics, an equity curve against buy-and-hold, and every simulated trade with the reason it fired. Strategies can be saved and reopened.

> **Disclaimer:** for research and education only. Backtests use past data from an unofficial source (Yahoo Finance) and simplified fills; they do not predict future results and are not financial advice.

- **Frontend:** React 19 + TypeScript + Vite + Tailwind v4 (`frontend/`)
- **Backend:** Python 3.10+ with FastAPI, pandas, numpy and yfinance (`backend/`)
- **Data:** daily prices from Yahoo Finance via `yfinance`

Detailed design and code flow: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Backend API reference: [backend/README.md](backend/README.md).

## Repository layout

```
alphabacktest/
├── README.md
├── docs/ARCHITECTURE.md        # flow diagrams and code walkthrough
├── backend/
│   ├── README.md               # API reference
│   ├── requirements.txt        # runtime; requirements-dev.txt adds test-only deps
│   ├── alphabacktest/
│   │   ├── api.py              # HTTP endpoints (FastAPI): backtest, symbol search
│   │   ├── strategies.py       # saved-strategy CRUD (scoped to the current user)
│   │   ├── db.py, orm.py       # SQLAlchemy session + tables (users, strategies)
│   │   ├── models.py           # request/response contract (Pydantic)
│   │   ├── data.py             # Yahoo Finance: prices + symbol search
│   │   ├── indicators.py       # SMA, EMA, RSI, Bollinger, MACD, volume
│   │   └── engine.py           # backtest simulation + metrics
│   └── tests/                  # engine, saved-strategy API, indicator cross-check (vs `ta`)
└── frontend/
    ├── vite.config.ts          # dev server; proxies /api to :8080
    └── src/
        ├── App.tsx             # screen state machine + run orchestration
        ├── api.ts              # fetch wrappers + error mapping
        ├── types.ts            # TypeScript mirror of the backend models
        ├── conditions.ts       # indicator/operator catalog, labels, validation
        ├── format.ts           # date / percent / currency formatting
        └── components/
            ├── StrategyBuilder.tsx   # main builder screen + client-side validation
            ├── SymbolPicker.tsx      # searchable stock dropdown
            ├── ConditionList.tsx     # AND-connected condition cards
            ├── ConditionModal.tsx    # add / edit a condition
            ├── Running.tsx           # in-progress screen
            ├── Results.tsx           # metrics, equity chart, trade table; also the Failed screen
            ├── EquityChart.tsx       # strategy vs buy & hold (SVG, hover, table view)
            ├── SavedStrategies.tsx   # saved list: open / delete
            ├── SaveDialog.tsx        # name + description when saving
            ├── TradeDrawer.tsx       # per-trade detail + "why did it trigger"
            └── ui.tsx                # Button, Section, Field, Stat, Modal
```

## Quick start

### Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.10 or newer (3.12 recommended) | `python3 --version` |
| Node.js | 18 or newer (with npm) | `node --version` |
| Internet access | needed for prices and symbol search (Yahoo Finance) | |

macOS and Linux commands are shown; on Windows use `py -3.12 -m venv .venv` and `.venv\Scripts\activate` for the virtual environment.

### 1. Clone

```bash
git clone https://github.com/nktanurag/alphabacktest.git
cd alphabacktest
```

### 2. Start the backend (terminal 1)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn alphabacktest.api:app --port 8080 --reload
```

Check it: open http://localhost:8080/api/health (should show `{"ok":true}`) or the interactive API docs at http://localhost:8080/docs.

Using [uv](https://docs.astral.sh/uv/) instead? `uv venv --python 3.12 .venv && uv pip install -r requirements.txt`, then run `.venv/bin/uvicorn alphabacktest.api:app --port 8080 --reload`.

The first start creates a SQLite database file, `backend/alphabacktest.db`, for saved strategies. No other setup is needed.

### 3. Start the frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The dev server forwards `/api` requests to the backend on port 8080.

> Run each command on its own line. Pasting a trailing `# comment` into zsh passes it to the program as arguments and can break the command.

### 4. Try it

1. Click the asset box and search for a stock (for example "apple").
2. Keep the default entry condition (`RSI(14) < 35`) or add your own with **+ Add Condition**.
3. Choose exit rules (holding period, stop-loss, take-profit, or an exit signal).
4. Click **Run Backtest**. You get metrics, the equity curve against buy-and-hold, and a trade table. Click a trade to see why it triggered.
5. Click **Save Strategy**, then find it later under **Saved Strategies**.

## Configuration

| Setting | Where | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | backend environment | `sqlite:///./alphabacktest.db` | Database for saved strategies. For Postgres: `postgresql+psycopg://user:pass@host/db` (also `pip install "psycopg[binary]"`) |
| `API_URL` | frontend environment | `http://localhost:8080` | Where the dev server proxies `/api` (for example `API_URL=http://localhost:9000 npm run dev`) |
| `--port` | `uvicorn` flag | 8080 | Backend port; keep it in sync with `API_URL` |

Other ports and hosts work too, as long as the frontend can reach the backend. There is no `.env` file; nothing secret is needed.

## Tests and checks

```bash
# backend (from backend/, with the virtual environment active)
pip install -r requirements-dev.txt     # adds the `ta` library used to cross-check indicators
python -m pytest

# frontend (from frontend/)
npm run build                           # type-check + production build
```

The backend tests run offline (no Yahoo access needed).

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| "Backtest could not be completed" right after clicking Run | Backend not running, or an old process on port 8080 with outdated code. Stop it and start it again (use `--reload` while developing) |
| "Search is unavailable right now" or "Historical market data could not be loaded" | Yahoo Finance is rate-limiting or unreachable (HTTP 429). Wait a few minutes and retry; results are cached for 6 hours once loaded |
| Saved strategies page shows an error | Backend not running or its database file is not writable. Check the terminal running `uvicorn` |
| `address already in use` | Another program uses the port. Use another one, for example `--port 8090` and `API_URL=http://localhost:8090 npm run dev` |
| `SyntaxError` / `match` errors starting the backend | Python older than 3.10. Install a newer Python and recreate the virtual environment |
| Vite warns that the project root contains `#` | You pasted a `# comment` after `npm run dev`. Run the command on its own |

## Features (current)

- Searchable stock/ETF picker (Yahoo search by ticker or company name)
- Any number of entry conditions, all ANDed; add / edit / delete with a remove confirmation
- Indicators: Price, SMA, EMA, RSI, Bollinger upper/lower, MACD, MACD signal, Volume (optionally averaged)
- Operators: crosses above, crosses below, greater than, less than, equals; compare to another indicator or a fixed value
- Exit rules, first to trigger wins: holding period, stop-loss, take-profit, and/or an exit signal built from conditions
- Execution settings: initial capital, position size, commission, slippage, entry timing (next open or signal close)
- Equity-curve chart of the strategy vs buy-and-hold (hover tooltip, table view), plus buy-and-hold return and drawdown
- Saved strategies: save / update, list, open, delete (per-user tables; no login yet, so everyone is one local user)
- Results: total return, CAGR, win rate, profit factor, max drawdown, Sharpe; trade summary; sortable/filterable trade table; per-trade drawer with entry reasons
- States: validation errors, running (cancellable), no trades, warnings, failure
- Prices and P&L shown in the asset's own currency (e.g. INR for `RELIANCE.NS`)

## Backtest rules (important for interpreting results)

- Long-only, one position at a time, all entry conditions ANDed
- Signals are evaluated on each day's close
- **Entry timing:** `next_open` (default) buys at the next day's open, avoiding look-ahead bias. `signal_close` buys at the signal day's close (slightly optimistic)
- Exits, checked each day in this order: a signal exit flagged the previous day (next-open mode); stop-loss; take-profit (both use the day's low/high, gaps fill at the open, and if one day could hit both the stop-loss is assumed first); the holding period; the end date (open trades close at that day's close, with a warning); a signal exit on today's close
- Entry timing also applies to signal exits
- Slippage worsens both fills; commission is charged on both sides
- Position size is a percentage of current cash
- Prices are split/dividend adjusted

## Known limitations

- No login (strategies aren't private yet), no export, no stored backtest runs, no database migrations (tables are auto-created)
- Buy-and-hold is shown before costs
- Yahoo Finance is an unofficial source: it can rate-limit (HTTP 429) or change without notice. Data failures show a friendly error; symbol search shows "Search is unavailable"
- Indicators are implemented in `indicators.py` with pandas/numpy; they are cross-checked against the `ta` library in tests (identical after warm-up; the first bars differ slightly because we seed EMA/RSI with an SMA)
- Profit factor uses currency P&L; some tools use summed return percentages, so values can differ slightly
- The frontend has no automated tests (it was click-tested in a real browser, but not with a repeatable suite)
- The frontend currently loads Google Fonts from the network

## Ideas for later

OR condition groups, parameter sweeps, login, stored runs, export.

## License

[MIT](LICENSE)
