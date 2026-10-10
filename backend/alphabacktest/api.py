import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import data
from .db import init_db
from .engine import run_backtest, validate_strategy
from .models import BacktestResult, Strategy
from .strategies import router as strategies_router

log = logging.getLogger("alphabacktest")
@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="AlphaBacktest", lifespan=lifespan)
app.include_router(strategies_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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
