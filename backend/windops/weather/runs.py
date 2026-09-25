"""Real ECMWF runs, their provenance, validated windows, and bounded recovery."""
from __future__ import annotations

import json
import pandas as pd
import numpy as np
import requests

from ..data.repository import iso

TURBINES = {"WT_1": (43.645139, 78.535611), "WT_2": (43.643194, 78.538833)}
HOURLY = ["temperature_2m", "relative_humidity_2m", "surface_pressure", "wind_speed_10m", "wind_speed_80m",
          "wind_speed_120m", "wind_direction_10m", "wind_direction_80m", "wind_direction_120m", "wind_gusts_10m"]
DELAY = pd.Timedelta(hours=6, minutes=10)


def window_from_snapshot(snapshot: dict, origin: pd.Timestamp) -> pd.DataFrame:
    run = pd.Timestamp(snapshot["run_initialization_utc"])
    if run + DELAY > origin:
        raise ValueError("This weather run was not available at the selected origin under the availability policy.")
    payload = snapshot["response"]
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError("Weather response must contain both turbine locations.")
    expected = pd.date_range(origin.floor("h") + pd.Timedelta(hours=1), periods=48, freq="h")
    frames = []
    for index, (name, item) in enumerate(zip(TURBINES, payload)):
        if item.get("location_id", index) != index:
            raise ValueError("Weather locations are in an unexpected order.")
        units = item.get("hourly_units", {})
        if any(units.get(key) != "m/s" for key in HOURLY if key.startswith(("wind_speed", "wind_gusts"))):
            raise ValueError("Weather wind units must be metres per second.")
        if units.get("temperature_2m") != "°C" or units.get("surface_pressure") != "hPa":
            raise ValueError("Unexpected weather temperature or pressure units.")
        frame = pd.DataFrame(item["hourly"])
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        frame = frame[frame.time.isin(expected)].sort_values("time").copy()
        if not pd.DatetimeIndex(frame.time).equals(expected):
            raise ValueError("The weather run does not cover all 48 requested hours.")
        if not np.isfinite(frame[HOURLY].to_numpy(dtype=float)).all():
            raise ValueError("Weather data contains missing values.")
        for column in HOURLY:
            if column.startswith(("wind_speed", "wind_gusts")) and (frame[column] < 0).any():
                raise ValueError("Weather data contains negative wind speeds.")
            if column.startswith("wind_direction") and not frame[column].between(0, 360).all():
                raise ValueError("Weather data contains invalid wind directions.")
        frame["turbine"] = name
        frame["forecast_horizon_hour"] = np.arange(1, 49)
        frame["lead_from_run_hours"] = (frame.time - run).dt.total_seconds() / 3600
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def fetch_live(settings, origin: pd.Timestamp, emit) -> tuple[dict, pd.DataFrame, str]:
    latest = (origin - DELAY).floor("6h")
    endpoint = "https://single-runs-api.open-meteo.com/v1/forecast"
    if settings.weather_key:
        endpoint = "https://customer-single-runs-api.open-meteo.com/v1/forecast"
    for attempt in range(2):
        run = latest - pd.Timedelta(hours=6 * attempt)
        emit("Weather", "Requesting weather run", f"ECMWF IFS · {iso(run)}", "running")
        params = {"latitude": ",".join(str(point[0]) for point in TURBINES.values()),
                  "longitude": ",".join(str(point[1]) for point in TURBINES.values()),
                  "models": "ecmwf_ifs", "run": run.strftime("%Y-%m-%dT%H:%M"), "hourly": ",".join(HOURLY),
                  "wind_speed_unit": "ms", "temperature_unit": "celsius", "timezone": "UTC", "timeformat": "unixtime",
                  "forecast_hours": 96}
        if settings.weather_key:
            params["apikey"] = settings.weather_key
        try:
            response = requests.get(endpoint, params=params, timeout=(10, 25))
            response.raise_for_status()
            snapshot = {"run_initialization_utc": iso(run), "retrieved_at_utc": iso(pd.Timestamp.now(tz="UTC")),
                        "response": response.json(), "weather_model": "ecmwf_ifs"}
            frame = window_from_snapshot(snapshot, origin)
            cache = settings.storage_dir / "weather" / "live-runs"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / f"{run.strftime('%Y%m%dT%H')}.json").write_text(json.dumps(snapshot, allow_nan=False), encoding="utf-8")
            return snapshot, frame, "Primary" if attempt == 0 else "Previous run"
        except (requests.RequestException, ValueError, KeyError, TypeError):
            emit("Weather", "Weather run unavailable", "Checking an earlier ECMWF run." if attempt == 0 else "Checking the local weather cache.", "warning")
    cache = settings.storage_dir / "weather" / "live-runs"
    for path in sorted(cache.glob("*.json"), reverse=True):
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            run = pd.Timestamp(snapshot["run_initialization_utc"])
            if origin - run > pd.Timedelta(hours=18):
                continue
            frame = window_from_snapshot(snapshot, origin)
            emit("Weather", "Cached weather run loaded", f"ECMWF IFS · {iso(run)}", "warning")
            return snapshot, frame, "Cached"
        except (ValueError, KeyError, OSError):
            continue
    raise RuntimeError("Weather data is temporarily unavailable. No current forecast can be calculated.")
