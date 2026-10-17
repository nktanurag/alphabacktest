import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from docqa import config as docqa_config, db as docqa_db
from docqa.api import router as docqa_router

from . import auth, data
from .db import init_db
from .engine import run_backtest, validate_strategy
from .models import BacktestResult, Strategy
from .strategies import router as strategies_router

log = logging.getLogger("alphabacktest")
@asynccontextmanager
async def lifespan(_: FastAPI):
    auth.check_config()
    init_db()
    if docqa_config.enabled():
        docqa_db.init_db()
    yield


app = FastAPI(title="AlphaBacktest", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(strategies_router)
app.include_router(docqa_router)
# No CORS middleware: the frontend is served from the same address as the API
# (or proxied to it by the Vite dev server), so browsers never make cross-origin calls.


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/symbols/search")
def symbol_search(q: str = ""):
    try:
        return data.search_symbols(q)
    except Exception:
        log.exception("symbol search failed")
        return JSONResponse(status_code=502, content={
            "error": "search_unavailable", "message": "Symbol search is unavailable right now."})


@app.post("/api/backtest", response_model=BacktestResult)
def backtest(strategy: Strategy):
    issues = validate_strategy(strategy)
    if issues:
        return JSONResponse(status_code=400, content={"error": "invalid_strategy", "issues": issues})
    try:
        df = data.fetch_daily_bars(strategy.asset, strategy.startDate, strategy.endDate)
    except Exception:
        log.exception("data fetch failed")
        return JSONResponse(status_code=502, content={
            "error": "data_unavailable", "message": "Historical market data could not be loaded."})
    try:
        return run_backtest(strategy, df)
    except Exception as e:
        log.exception("backtest failed")
        return JSONResponse(status_code=422, content={"error": "backtest_failed", "message": str(e)})


# Serve the built frontend (npm run build -> frontend/dist) from the same server, so one
# deployment hosts everything. Mounted last so every /api route above wins. Absent in
# development, where the Vite dev server serves the UI instead.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
