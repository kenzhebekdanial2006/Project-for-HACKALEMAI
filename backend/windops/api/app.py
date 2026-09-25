"""WindOps HTTP API. Run one worker; the scheduler owns model execution."""
from contextlib import asynccontextmanager
from typing import Literal
import logging
import secrets

import pandas as pd
from fastapi import FastAPI, Header, HTTPException
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..agent.copilot import answer_question
from ..core.config import settings
from ..data.telemetry import TelemetryBatch
from .runtime import Runtime

runtime = Runtime(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime.start()
    yield
    runtime.stop.set()


app = FastAPI(title="WindOps API", version="2.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    if request.url.path == "/api/telemetry":
        # Malformed NaN/Infinity values must not cause a second serialization
        # error while the validation handler echoes the original sender input.
        return JSONResponse(status_code=422, content={"detail": "Invalid turbine readings. Check turbine IDs, timestamps and measurement units."})
    return await request_validation_exception_handler(request, error)


@app.exception_handler(Exception)
async def unexpected_error(request, error):
    logging.getLogger(__name__).warning("API operation failed (%s)", type(error).__name__)
    return JSONResponse(status_code=500, content={"detail": "The operation could not be completed. Check the server data configuration."})


@app.get("/api/health")
def health():
    return {"status": "online", "modelLoaded": runtime.forecaster is not None}


@app.get("/api/operations")
def operations():
    return runtime.snapshot()


@app.get("/api/forecast")
def forecast():
    result = runtime.snapshot()["forecast"]
    if result is None:
        raise HTTPException(503, "A forecast is not available yet. Check the agent event log.")
    return result


@app.get("/api/weather")
def weather():
    return [{key: value for key, value in row.items() if key not in {"WT01", "WT02"}} for row in forecast()["records"]]


@app.get("/api/turbines")
def turbines():
    return runtime.snapshot()["turbines"]


@app.get("/api/telemetry", tags=["Telemetry"])
def telemetry():
    return runtime.telemetry.snapshot()


@app.post("/api/telemetry", tags=["Telemetry"])
def receive_telemetry(body: TelemetryBatch, x_telemetry_key: str = Header(default="")):
    if runtime.telemetry.file_mode:
        raise HTTPException(409, "A telemetry file is configured. Update that file to publish measurements.")
    expected = runtime.settings.telemetry_key
    if not expected:
        raise HTTPException(503, "Telemetry ingestion is not configured. Set WINDOPS_TELEMETRY_KEY on the server.")
    if not secrets.compare_digest(x_telemetry_key.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(401, "A valid telemetry key is required.")
    try:
        result = runtime.telemetry.ingest(body)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    runtime.check_telemetry()
    return result


@app.get("/api/anomalies")
def anomalies():
    return runtime.snapshot()["anomalies"]


@app.get("/api/agent/status")
def agent_status():
    return runtime.snapshot()["agent"]


@app.get("/api/agent/history")
def agent_history():
    return runtime.snapshot()["events"]


@app.get("/api/diagnostics")
def diagnostics():
    result = runtime.diagnostics()
    if result is None:
        raise HTTPException(503, "Model and dataset information is not available yet.")
    return result


@app.post("/api/forecast/refresh", status_code=202)
def refresh():
    started = runtime.start_refresh()
    return {"started": started, "busy": True}


class ReplayRequest(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}$")


@app.post("/api/replay")
def replay(body: ReplayRequest):
    try:
        origin = pd.Timestamp(f"{body.date}T{body.time}:00Z")
        return runtime.replay(origin)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@app.get("/api/forecast/explanation")
def explanation(forecast_id: str, timestamp: str, turbine: Literal["WT01", "WT02"]):
    try:
        return runtime.explanation(forecast_id, timestamp, turbine)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


class CopilotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class CopilotRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    locale: Literal["en", "ru", "kk"] = "en"
    history: list[CopilotMessage] = Field(default_factory=list, max_length=12)
    forecastId: str | None = Field(default=None, min_length=1, max_length=64)


@app.post("/api/copilot")
def copilot(body: CopilotRequest):
    snapshot = runtime.snapshot()
    if snapshot["forecast"] is None:
        raise HTTPException(503, "A forecast is not available yet. Check the agent event log.")
    if body.forecastId is not None and body.forecastId != snapshot["forecast"]["id"]:
        raise HTTPException(409, "The forecast changed. Ask again using the latest data.")
    return answer_question(body.question.strip(), snapshot["forecast"], runtime.settings, body.locale,
                           snapshot["turbines"], history=[item.model_dump() for item in body.history],
                           diagnostics=snapshot["diagnostics"])
