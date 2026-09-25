"""Read the supplied research artifacts without modifying or retraining them."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

LOCAL_TIMEZONE = "Asia/Almaty"


def iso(value) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")


class ArtifactRepository:
    def __init__(self, root: Path):
        self.root = root
        self.metadata = json.loads((root / "models/catboost_weather_metadata.json").read_text(encoding="utf-8"))
        self.model_path = root / "models/catboost_weather.cbm"
        self.validation = pd.read_csv(root / "models/weather_validation_predictions.csv")
        self.hourly = pd.read_csv(root / "data/processed/hourly_training.csv")
        # Training code explicitly treats SCADA timestamps as local, not UTC.
        local = pd.to_datetime(self.hourly["timestamp"], format="mixed")
        self.hourly["time_utc"] = local.dt.tz_localize(LOCAL_TIMEZONE, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
        self.hourly = self.hourly.dropna(subset=["time_utc", "power", "wind_speed", "temperature"])
        end = pd.Timestamp(self.metadata["training_target_period"]["end"])
        # Targets label the START of an hourly aggregation bucket. Wait for the
        # complete final training hour before allowing a historical origin.
        self.trained_through = end.tz_localize(LOCAL_TIMEZONE).tz_convert("UTC") + pd.Timedelta(hours=1)
        self.interval_errors = {}
        for turbine, group in self.validation.groupby("turbine"):
            residual = (group["power"] - group["prediction"]).abs()
            self.interval_errors[turbine] = float(residual.quantile(.9))
        self.datasets = []
        for index in [1, 2]:
            path = root / f"data/turbine_{index}.csv"
            with path.open(encoding="utf-8-sig") as stream:
                count = sum(1 for _ in stream) - 1
            group = self.hourly[self.hourly.turbine == f"WT_{index}"]
            latest = group.sort_values("time_utc").iloc[-1]
            self.datasets.append({
                "id": f"WT-0{index}", "records": count, "hourlyRecords": len(group),
                "start": iso(group.time_utc.min()), "end": iso(group.time_utc.max()),
                "lastObservation": {"timestamp": iso(latest.time_utc), "power": float(latest.power),
                                    "wind": float(latest.wind_speed), "temperature": float(latest.temperature)},
            })
        self.archives = []
        for file in sorted((root / "weather_backtest").glob("*/response.json")):
            snapshot = json.loads(file.read_text(encoding="utf-8"))
            run = pd.Timestamp(snapshot["run_initialization_utc"])
            self.archives.append((run, file))
        self.anomalies = self._historical_deviations()
        self._training_weather = None

    def _historical_deviations(self) -> list[dict]:
        one = self.hourly[self.hourly.turbine == "WT_1"].set_index("time_utc")
        two = self.hourly[self.hourly.turbine == "WT_2"].set_index("time_utc")
        joined = one[["power", "wind_speed"]].join(two[["power", "wind_speed"]], lsuffix="_1", rsuffix="_2", how="inner")
        joined = joined[joined.index >= joined.index.max() - pd.Timedelta(days=90)]
        signals = []
        for index, other in [(1, 2), (2, 1)]:
            mask = ((joined.wind_speed_1 - joined.wind_speed_2).abs() <= .8) & (joined[f"power_{other}"] - joined[f"power_{index}"] >= .2)
            start = previous = None
            for timestamp in joined.index[mask]:
                if previous is not None and timestamp - previous > pd.Timedelta(hours=1):
                    if previous > start:
                        signals.append(self._deviation(index, start, previous))
                    start = None
                if start is None:
                    start = timestamp
                previous = timestamp
            if start is not None and previous > start:
                signals.append(self._deviation(index, start, previous))
        return sorted(signals, key=lambda item: item["date"], reverse=True)[:12]

    @staticmethod
    def _deviation(index, start, end):
        return {"id": f"archive-{index}-{int(start.timestamp())}", "date": iso(start),
                "turbine": f"WT-0{index}", "title": "Historical power divergence", "active": False,
                "duration": f"{int((end - start).total_seconds() / 3600) + 1} h", "end": iso(end)}

    def archive_for(self, origin: pd.Timestamp) -> dict:
        if origin <= self.trained_through:
            raise ValueError("The selected origin precedes the model training cutoff. Choose a later date.")
        # Availability is a documented estimate from the supplied research code.
        eligible = [(run, path) for run, path in self.archives if run + pd.Timedelta(hours=6, minutes=10) <= origin]
        if not eligible:
            raise ValueError("No archived weather run is available before the selected origin.")
        run, path = eligible[-1]
        if origin - run > pd.Timedelta(hours=48):
            raise ValueError("No archived weather run covers the selected date. Choose a date in February 2026.")
        return json.loads(path.read_text(encoding="utf-8"))

    def similar_periods(self, weather: dict, turbine: str, origin: pd.Timestamp) -> dict:
        if self._training_weather is None:
            columns = ["timestamp", "turbine", "decision_time_utc", "wind_speed_120m", "temperature_2m", "wind_direction_120m", "power"]
            data = pd.read_csv(self.root / "data/processed/training_v2.csv", usecols=columns)
            data["time_utc"] = pd.to_datetime(data.timestamp).dt.tz_localize(LOCAL_TIMEZONE).dt.tz_convert("UTC")
            data["decision_time_utc"] = pd.to_datetime(data.decision_time_utc, utc=True)
            self._training_weather = data.sort_values("decision_time_utc").drop_duplicates(["timestamp", "turbine"], keep="last")
        data = self._training_weather
        angular_distance = abs((data.wind_direction_120m - weather["windDirection"] + 180) % 360 - 180)
        matches = data[(data.turbine == turbine) & (data.time_utc < origin) & (data.decision_time_utc < origin)
                       & ((data.wind_speed_120m - weather["windSpeed120m"]).abs() <= 1.5)
                       & ((data.temperature_2m - weather["temperature"]).abs() <= 4)
                       & (angular_distance <= 45)]
        values = matches.power
        return {"historicalCount": len(matches), "historicalAverage": float(values.mean()) if len(values) else None,
                "historicalLower": float(values.quantile(.1)) if len(values) else None,
                "historicalUpper": float(values.quantile(.9)) if len(values) else None,
                "periods": [{"timestamp": iso(row.time_utc), "power": float(row.power)} for row in matches.tail(8).itertuples()]}
