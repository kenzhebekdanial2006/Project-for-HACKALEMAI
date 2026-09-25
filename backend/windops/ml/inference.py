"""Inference compatible with task/predict_february.py; no training at startup."""
from __future__ import annotations

import hashlib
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

from ..data.repository import LOCAL_TIMEZONE


def build_features(weather: pd.DataFrame) -> pd.DataFrame:
    data = weather.copy()
    local = pd.to_datetime(data["time"], utc=True).dt.tz_convert(LOCAL_TIMEZONE)
    data["hour_sin"] = np.sin(2 * np.pi * local.dt.hour / 24)
    data["hour_cos"] = np.cos(2 * np.pi * local.dt.hour / 24)
    data["day_sin"] = np.sin(2 * np.pi * local.dt.dayofyear / 365.25)
    data["day_cos"] = np.cos(2 * np.pi * local.dt.dayofyear / 365.25)
    for height in ["10m", "80m", "120m"]:
        radians = np.deg2rad(data[f"wind_direction_{height}"])
        data[f"wind_direction_{height}_sin"] = np.sin(radians)
        data[f"wind_direction_{height}_cos"] = np.cos(radians)
    for high, low in [(80, 10), (120, 80), (120, 10)]:
        data[f"wind_shear_{high}_{low}"] = data[f"wind_speed_{high}m"] - data[f"wind_speed_{low}m"]
    for height in [80, 120]:
        data[f"wind_speed_{height}m_cubed"] = data[f"wind_speed_{height}m"] ** 3
    return data


class Forecaster:
    def __init__(self, repository):
        self.repository = repository
        self.features = repository.metadata["features"]
        self.model = CatBoostRegressor()
        self.model.load_model(str(repository.model_path))
        if self.model.feature_names_ != self.features:
            raise ValueError("Model features do not match the supplied metadata.")
        self.fingerprint = hashlib.sha256(repository.model_path.read_bytes()).hexdigest()

    def predict(self, weather: pd.DataFrame) -> pd.DataFrame:
        frame = build_features(weather)
        numeric = frame[[name for name in self.features if name != "turbine"]]
        if not np.isfinite(numeric.to_numpy(dtype=float)).all():
            raise ValueError("Weather data contains missing or invalid model inputs.")
        frame["prediction"] = np.clip(self.model.predict(frame[self.features], thread_count=2), 0, 1)
        return frame

    def explain(self, frame: pd.DataFrame, timestamp: str, turbine: str) -> list[dict]:
        selected = frame[(frame.time == pd.Timestamp(timestamp)) & (frame.turbine == turbine)]
        if len(selected) != 1:
            raise ValueError("The selected forecast hour is not available.")
        pool = Pool(selected[self.features], cat_features=["turbine"])
        contributions = self.model.get_feature_importance(pool, type="ShapValues", thread_count=2)[0][:-1]
        groups = {}
        for feature, value in zip(self.features, contributions):
            if "direction" in feature:
                label = "Wind direction"
            elif "shear" in feature:
                label = "Wind variation by height"
            elif feature.startswith("wind_speed_"):
                label = "Wind speed " + feature.split("_")[2]
            elif feature == "temperature_2m":
                label = "Temperature"
            elif feature == "surface_pressure":
                label = "Pressure"
            elif feature == "relative_humidity_2m":
                label = "Humidity"
            elif feature == "wind_gusts_10m":
                label = "Gusts"
            elif feature == "turbine":
                label = "Turbine response"
            else:
                label = "Time and forecast horizon"
            groups[label] = groups.get(label, 0) + float(value)
        scale = max(sum(abs(value) for value in groups.values()), .000001)
        return [{"label": label, "value": round(abs(value) / scale * 100, 1), "contribution": round(value * 100, 2),
                 "negative": value < 0, "note": "Negative impact" if value < 0 else "Positive impact"}
                for label, value in sorted(groups.items(), key=lambda item: abs(item[1]), reverse=True)[:6]]
