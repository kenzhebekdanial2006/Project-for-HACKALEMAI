from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from forecast_live import generate_live_forecast
from ai_agent import analyze_live_forecast


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

LIVE_JSON = (
    BASE_DIR
    / "predictions"
    / "live"
    / "forecast_live.json"
)

ANALYSIS_JSON = (
    BASE_DIR
    / "predictions"
    / "live"
    / "analysis_live.json"
)


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Wind AI API",
    description=(
        "Agentic AI system for 24–48 hour "
        "wind power forecasting"
    ),
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# ============================================================
# HELPERS
# ============================================================

def read_json(path: Path) -> dict:

    if not path.exists():

        raise FileNotFoundError(
            f"Файл не найден: {path}"
        )

    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(data, dict):
        raise ValueError("Ожидался JSON-объект.")
    return data


def run_full_pipeline() -> dict:
    """
    Полный Agentic AI цикл:

    1. ECMWF weather
    2. Feature engineering
    3. CatBoost prediction
    4. OpenAI analysis
    5. Save results
    """

    # Weather + ML
    generate_live_forecast()

    # AI analysis
    analysis = analyze_live_forecast()

    forecast = read_json(
        LIVE_JSON
    )

    return {
        "status": "success",

        "message": (
            "Полный прогнозный цикл выполнен."
        ),

        "generated_at_utc": (
            forecast.get(
                "generated_at_utc"
            )
        ),

        "weather_run_utc": (
            forecast.get(
                "weather_run_utc"
            )
        ),

        "forecast_count": (
            forecast.get(
                "forecast_count"
            )
        ),

        "power_model": (
            forecast.get(
                "power_model"
            )
        ),

        "agent": (
            analysis.get(
                "agent_model"
            )
        ),

        "analysis_summary": (
            analysis
            .get(
                "analysis",
                {}
            )
            .get(
                "summary"
            )
        ),

        "recalculate": (
            analysis
            .get(
                "analysis",
                {}
            )
            .get(
                "recalculate"
            )
        ),
    }


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "service": "Wind AI",
        "status": "running",
        "docs": "/docs",
    }


# ============================================================
# STATUS
# ============================================================

@app.get("/api/status")
def status():

    forecast_available = (
        LIVE_JSON.exists()
    )

    analysis_available = (
        ANALYSIS_JSON.exists()
    )

    forecast_generated_at = None
    analysis_generated_at = None

    if forecast_available:

        try:

            forecast = read_json(
                LIVE_JSON
            )

            forecast_generated_at = (
                forecast.get(
                    "generated_at_utc"
                )
            )

        except Exception:

            pass

    if analysis_available:

        try:

            analysis = read_json(
                ANALYSIS_JSON
            )

            analysis_generated_at = (
                analysis.get(
                    "generated_at_utc"
                )
            )

        except Exception:

            pass

    return {
        "status": "ok",

        "backend": "online",

        "weather_source": (
            "ECMWF IFS HRES"
        ),

        "power_model": (
            "catboost_weather_v2"
        ),

        "ai_agent": "OpenAI",

        "forecast_available": (
            forecast_available
        ),

        "analysis_available": (
            analysis_available
        ),

        "forecast_generated_at": (
            forecast_generated_at
        ),

        "analysis_generated_at": (
            analysis_generated_at
        ),

        "server_time_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }


# ============================================================
# FORECAST
# ============================================================

@app.get("/api/forecast/latest")
def forecast_latest():

    try:

        return read_json(
            LIVE_JSON
        )

    except FileNotFoundError:

        raise HTTPException(
            status_code=404,
            detail=(
                "Live forecast ещё не создан. "
                "Выполните POST /api/recalculate"
            ),
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


# ============================================================
# FORECAST BY TURBINE
# ============================================================

@app.get(
    "/api/forecast/latest/{turbine}"
)
def forecast_turbine(
    turbine: str,
):

    turbine = turbine.upper()

    if turbine not in {
        "WT_1",
        "WT_2",
    }:

        raise HTTPException(
            status_code=404,
            detail=(
                "Используйте WT_1 или WT_2."
            ),
        )

    try:

        data = read_json(
            LIVE_JSON
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )

    forecasts = [

        item

        for item in data[
            "forecasts"
        ]

        if item[
            "turbine"
        ] == turbine
    ]

    return {
        "status": "ok",

        "generated_at_utc": (
            data.get(
                "generated_at_utc"
            )
        ),

        "weather_run_utc": (
            data.get(
                "weather_run_utc"
            )
        ),

        "power_model": (
            data.get(
                "power_model"
            )
        ),

        "turbine": turbine,

        "horizon_hours": (
            data.get(
                "horizon_hours"
            )
        ),

        "forecast_count": len(
            forecasts
        ),

        "forecasts": forecasts,
    }


# ============================================================
# AI ANALYSIS
# ============================================================

@app.get("/api/analysis/latest")
def analysis_latest():

    try:

        return read_json(
            ANALYSIS_JSON
        )

    except FileNotFoundError:

        raise HTTPException(
            status_code=404,
            detail=(
                "AI-анализ ещё не создан. "
                "Выполните POST "
                "/api/analysis/recalculate"
            ),
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


# ============================================================
# ONLY AI RECALCULATION
# ============================================================

@app.post(
    "/api/analysis/recalculate"
)
async def analysis_recalculate():

    try:

        result = await run_in_threadpool(
            analyze_live_forecast
        )

        return result

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


# ============================================================
# FULL AGENTIC RECALCULATION
# ============================================================

@app.post("/api/recalculate")
async def recalculate():

    try:

        return await run_in_threadpool(
            run_full_pipeline
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )
