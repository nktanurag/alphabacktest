# AlphaBacktest

A no-code historical strategy backtester. Pick a stock, define entry conditions (any number, combined with AND) and exit rules (holding period, stop-loss, take-profit, exit signal), and see how the strategy would have performed: metrics, an equity curve against buy-and-hold, and every simulated trade with the reason it fired. Strategies can be saved and reopened. An optional **Documents** tab adds Document Q&A: upload annual-report PDFs and ask questions, with local search and (optionally) Gemini-written answers that cite their sources.

<img width="1182" height="1244" alt="image" src="https://github.com/user-attachments/assets/40267afb-06fc-446a-b6ca-2592b1ff1b46" />

<img width="1192" height="424" alt="image" src="https://github.com/user-attachments/assets/5ce09c69-1ccf-48dd-8068-5619ebdf7881" />

<img width="828" height="1424" alt="image" src="https://github.com/user-attachments/assets/ca078872-a9ff-47f2-9ef0-3fe05f2eab1a" />


> **Disclaimer:** for research and education only. Backtests use past data from an unofficial source (Yahoo Finance) and simplified fills; they do not predict future results and are not financial advice.

- **Frontend:** React 19 + TypeScript + Vite + Tailwind v4 (`frontend/`)
- **Backend:** Python 3.10+ with FastAPI, pandas, numpy and yfinance (`backend/`)
- **Data:** daily prices from Yahoo Finance via `yfinance`

Hosting it on the internet: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Detailed design and code flow: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Backend API reference: [backend/README.md](backend/README.md). Document Q&A (upload PDFs and ask questions, optional): setup, design and status in [docs/DOCQA.md](docs/DOCQA.md), evaluation plan in [docs/DOCQA_EVAL.md](docs/DOCQA_EVAL.md).

## Repository layout

```
alphabacktest/
├── README.md
├── docs/ARCHITECTURE.md        # flow diagrams and code walkthrough
├── docs/DOCQA.md               # Document Q&A: setup, design, status
├── docs/DOCQA_EVAL.md          # Document Q&A: retrieval evaluation plan
├── backend/
│   ├── README.md               # API reference
│   ├── requirements.txt        # runtime; requirements-dev.txt adds test-only deps
│   ├── docqa/                  # Document Q&A (separate package, optional): upload, chunk, embed, search, rerank, answer
│   ├── alphabacktest/
│   │   ├── api.py              # HTTP endpoints (FastAPI): backtest, symbol search
│   │   ├── auth.py             # Google sign-in, session cookie, current_user()
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
            ├── SignInDialog.tsx      # "sign in to continue" prompt
            ├── GoogleButton.tsx      # Google's sign-in button (loads their script)
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

### 5. Optional: Document Q&A (the Documents tab)

Off by default; the backtester works without it. It needs **Postgres 17 or 18 with the pgvector extension** (a second database, separate from the strategies one) and about 700 MB of disk for two models that download on first use and run on your CPU. **No API key is needed to search.** A free [Gemini API key](https://aistudio.google.com/apikey) is needed only for the optional "Generate an answer" box; when you use it, your question and the top passages are sent to Google (on the free tier Google may use them to improve its products).

```bash
# macOS example; other systems and Docker: docs/DOCQA.md
brew install postgresql@18 pgvector
brew services start postgresql@18
/opt/homebrew/opt/postgresql@18/bin/createdb docqa

# in the SAME terminal that starts the backend, from backend/
export DOCQA_DATABASE_URL=postgresql://localhost/docqa
export GEMINI_API_KEY=your-key-here        # optional
uvicorn alphabacktest.api:app --port 8080 --reload
```

Check `curl localhost:8080/api/docqa/config` shows `"enabled": true`, then open the **Documents** tab. Full setup, a model-cache tip and troubleshooting: [docs/DOCQA.md](docs/DOCQA.md).

## Configuration

| Setting | Where | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | backend environment | `sqlite:///./alphabacktest.db` | Database for saved strategies. For Postgres: `postgresql+psycopg://user:pass@host/db` (also `pip install "psycopg[binary]"`) |
| `API_URL` | frontend environment | `http://localhost:8080` | Where the dev server proxies `/api` (for example `API_URL=http://localhost:9000 npm run dev`) |
| `--port` | `uvicorn` flag | 8080 | Backend port; keep it in sync with `API_URL` |
| `GOOGLE_CLIENT_ID` | backend environment | unset | Turns on Google sign-in. Unset = no login, everyone shares one local user |
| `SESSION_SECRET` | backend environment | unset | Long random string that signs session cookies. Required when `GOOGLE_CLIENT_ID` is set |
| `COOKIE_SECURE` | backend environment | off | Set to `1` when serving over HTTPS so the cookie is only sent securely |
| `DOCQA_DATABASE_URL` | backend environment | unset (feature off) | Postgres with pgvector for Document Q&A, e.g. `postgresql://localhost/docqa`. More `DOCQA_*` settings and `GEMINI_API_KEY`: [docs/DOCQA.md](docs/DOCQA.md) |

Other ports and hosts work too, as long as the frontend can reach the backend. There is no `.env` file; settings are plain environment variables, and none are needed unless you turn on Google sign-in or Document Q&A. Set them in the terminal that starts the backend, before it starts.

### Google sign-in (optional)

Without it the app works as before, with one shared local user. To make strategies private to each Google account:

1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials), create an **OAuth client ID** of type **Web application** (configure the consent screen first if asked).
2. Under **Authorized JavaScript origins**, add `http://localhost:5173` (and your real site URL when you deploy). No redirect URI is needed.
3. Start the backend with the client ID and a random secret:

```bash
export GOOGLE_CLIENT_ID="1234-abc.apps.googleusercontent.com"
export SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
uvicorn alphabacktest.api:app --port 8080 --reload
```

Paste the client ID exactly as Google shows it; it already ends in `.apps.googleusercontent.com`, so don't add that again. Check with `curl -s localhost:8080/api/auth/config`. If the consent screen is in "Testing" mode, add your Google address under **Test users**. Google errors such as `invalid_client` (wrong or mistyped ID) or `origin_mismatch` (the page's address isn't in Authorized JavaScript origins) come from Google, not this app.

Keep `SESSION_SECRET` the same between restarts, or everyone is signed out. Strategies saved before login was on belong to the shared local user and are not shown to Google accounts.

## Tests and checks

```bash
# backend (from backend/, with the virtual environment active)
pip install -r requirements-dev.txt     # adds `ta` (indicator cross-check) and `reportlab` (builds test PDFs)
python -m pytest

# frontend (from frontend/)
npm run build                           # type-check + production build
```

The backend tests run offline (no Yahoo access needed). The Document Q&A tests need a local Postgres with pgvector and an empty database named `docqa_test` (`createdb docqa_test`; override with `DOCQA_TEST_DATABASE_URL`); without it they are skipped. They use fake models, so no key or download is needed.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| "Backtest could not be completed" right after clicking Run | Backend not running, or an old process on port 8080 with outdated code. Stop it and start it again (use `--reload` while developing) |
| "Search is unavailable right now" or "Historical market data could not be loaded" | Yahoo Finance is rate-limiting or unreachable (HTTP 429). Wait a few minutes and retry; results are cached for 6 hours once loaded |
| Saved strategies page shows an error | Backend not running or its database file is not writable. Check the terminal running `uvicorn` |
| `address already in use` | Another program uses the port. Use another one, for example `--port 8090` and `API_URL=http://localhost:8090 npm run dev` |
| `SyntaxError` / `match` errors starting the backend | Python older than 3.10. Install a newer Python and recreate the virtual environment |
| No **Documents** tab, or Document Q&A errors | `DOCQA_DATABASE_URL` was not set in the terminal that started the backend, or Postgres lacks pgvector. See the troubleshooting table in [docs/DOCQA.md](docs/DOCQA.md) |
| Vite warns that the project root contains `#` | You pasted a `# comment` after `npm run dev`. Run the command on its own |

## Features (current)

- Searchable stock/ETF picker (Yahoo search by ticker or company name)
- Any number of entry conditions, all ANDed; add / edit / delete with a remove confirmation
- Indicators: Price, SMA, EMA, RSI, Bollinger upper/lower, MACD, MACD signal, Volume (optionally averaged)
- Operators: crosses above, crosses below, greater than, less than, equals; compare to another indicator or a fixed value
- Exit rules, first to trigger wins: holding period, stop-loss, take-profit, and/or an exit signal built from conditions
- Execution settings: initial capital, position size, commission, slippage, entry timing (next open or signal close)
- Equity-curve chart of the strategy vs buy-and-hold (hover tooltip, table view), plus buy-and-hold return and drawdown
- Saved strategies: save / update, list, open, delete. With Google sign-in on they are private to your account; with it off everyone shares one local user
- Results: total return, CAGR, win rate, profit factor, max drawdown, Sharpe; trade summary; sortable/filterable trade table; per-trade drawer with entry reasons
- States: validation errors, running (cancellable), no trades, warnings, failure
- Prices and P&L shown in the asset's own currency (e.g. INR for `RELIANCE.NS`)
- Document Q&A (optional): upload PDFs; hybrid search (meaning + keywords), reranking, adjustable chunking and cutoff, ranking shown before and after reranking, optional cited answers from Gemini

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

- Login is optional and Google-only (no email/password), no export, no stored backtest runs, no database migrations (tables are auto-created)
- Buy-and-hold is shown before costs
- Yahoo Finance is an unofficial source: it can rate-limit (HTTP 429) or change without notice. Data failures show a friendly error; symbol search shows "Search is unavailable"
- Indicators are implemented in `indicators.py` with pandas/numpy; they are cross-checked against the `ta` library in tests (identical after warm-up; the first bars differ slightly because we seed EMA/RSI with an SMA)
- Profit factor uses currency P&L; some tools use summed return percentages, so values can differ slightly
- The frontend has no automated tests (it was click-tested in a real browser, but not with a repeatable suite)
- The frontend currently loads Google Fonts from the network

## Ideas for later

OR condition groups, parameter sweeps, stored runs, export.

## License

[MIT](LICENSE)
