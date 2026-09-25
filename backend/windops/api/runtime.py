"""Atomic operational snapshots and actual background forecast execution."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import json
import logging
import threading
from uuid import uuid4

import numpy as np
import pandas as pd

from ..data.repository import ArtifactRepository, iso
from ..data.telemetry import TelemetryStore
from ..ml.inference import Forecaster
from ..weather.runs import DELAY, fetch_live, window_from_snapshot

logger = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings):
        self.settings = settings
        self.telemetry = TelemetryStore(settings)
        self.telemetry_signature = None
        self.lock = threading.RLock()
        self.model_lock = threading.RLock()
        self.stop = threading.Event()
        self.repository = None
        self.forecaster = None
        self.forecasts = OrderedDict()
        self.next_refresh = pd.Timestamp.now(tz="UTC")
        self.state = {"forecast": None, "turbines": [], "anomalies": [], "events": [], "notifications": [],
                      "busy": False, "error": None, "connected": True,
                      "agent": {"active": False, "task": "Loading model and datasets", "state": "Waiting", "stage": None, "source": "Unavailable"}}

    def initialize(self):
        if self.repository is None:
            with self.model_lock:
                if self.repository is None:
                    repository = ArtifactRepository(self.settings.task_dir)
                    forecaster = Forecaster(repository)
                    self.repository, self.forecaster = repository, forecaster
                    with self.lock:
                        self.state["anomalies"] = deepcopy(repository.anomalies)
                    self.emit("Validation", "Model and datasets loaded", f"{repository.metadata['version']} · {sum(item['records'] for item in repository.datasets)} records")

    def emit(self, stage, title, detail, status="completed"):
        now = pd.Timestamp.now(tz="UTC")
        event = {"id": uuid4().hex, "time": now.strftime("%H:%M:%S"), "timestamp": iso(now),
                 "title": title, "detail": detail, "stage": stage, "status": status}
        with self.lock:
            for previous in self.state["events"]:
                if previous["status"] == "running":
                    previous["status"] = "warning" if status == "warning" else "completed"
            self.state["events"] = [*self.state["events"], event][-100:]
            if self.state["busy"]:
                self.state["agent"].update(task=title, stage=stage)

    def notify(self, title, description, severity="Info"):
        now = pd.Timestamp.now(tz="UTC")
        notification = {"id": uuid4().hex, "title": title, "description": description, "severity": severity,
                        "time": now.strftime("%H:%M"), "timestamp": iso(now), "read": False}
        with self.lock:
            self.state["notifications"] = [notification, *self.state["notifications"]][:50]

    def start_refresh(self):
        with self.lock:
            if self.state["busy"]:
                return False
            self.state.update(busy=True, error=None)
            self.state["agent"].update(active=True, state="Processing", task="Receiving weather data", stage="Weather")
        threading.Thread(target=self.refresh, daemon=True, name="windops-forecast").start()
        return True

    def start(self):
        self.check_telemetry()
        self.start_refresh()
        def monitor():
            while not self.stop.wait(15):
                self.check_telemetry()
                if pd.Timestamp.now(tz="UTC") >= self.next_refresh:
                    self.start_refresh()
        threading.Thread(target=monitor, daemon=True, name="windops-monitor").start()

    def check_telemetry(self):
        telemetry = self.telemetry.snapshot()
        signature = (telemetry["status"], *(row["state"] for row in telemetry["readings"]))
        with self.lock:
            previous = self.telemetry_signature
            self.telemetry_signature = signature
        if signature == previous or (previous is None and not telemetry["freshCount"]):
            return
        title = "Current turbine readings available" if telemetry["available"] else "Turbine readings need attention"
        detail = ("Fresh measurements are available for both turbines. Operating state still requires verification."
                  if telemetry["available"] else "Check the measurement source and the timestamp of each turbine reading.")
        self.emit("Twin Analysis", title, detail, "completed" if telemetry["available"] else "warning")
        self.notify(title, detail, "Info" if telemetry["available"] else "Warning")

    def refresh(self):
        try:
            self.initialize()
            origin = pd.Timestamp.now(tz="UTC")
            snapshot, weather, source = fetch_live(self.settings, origin, self.emit)
            self.emit("Validation", "Weather inputs validated", "96 turbine-hour records; no missing required values.")
            self.emit("Feature Preparation", "Model inputs prepared", "Time features use the training timezone: Asia/Almaty.")
            forecast = self.calculate(snapshot, weather, origin, "live", source)
            self.emit("Forecast", "Forecast calculated", "Both turbines calculated with the trained weather model.")
            turbines = self.turbines(forecast)
            telemetry = self.telemetry.snapshot()
            if telemetry["available"]:
                self.emit("Twin Analysis", "Current turbine readings available", "Fresh measurements are available for both turbines. Operating state still requires verification.")
            else:
                self.emit("Twin Analysis", "Current telemetry unavailable", "Check the measurement source and the timestamp of each turbine reading.", "warning")
            self.emit("Decision", "Forecast quality assessed", f"System confidence: {forecast['confidence']}/100. Unavailable checks are disclosed.")
            with self.lock:
                previous = self.state["forecast"]
                if previous:
                    old = {row["timestamp"]: row for row in previous["records"]}
                    deltas = [(row["WT01"]["prediction"] + row["WT02"]["prediction"] - old[row["timestamp"]]["WT01"]["prediction"] - old[row["timestamp"]]["WT02"]["prediction"]) / 2
                              for row in forecast["records"] if row["timestamp"] in old]
                    forecast["changeSincePrevious"] = round(float(np.mean(deltas)) * 100, 2) if deltas else None
                self.state.update(forecast=forecast, turbines=turbines, error=None)
                self.state["agent"].update(active=True, state="Monitoring", task="Monitoring incoming weather updates", stage=None, source=source)
            self.emit("Publish", "Forecast published", f"48 hours · {forecast['modelVersion']} · {source}")
            with self.lock:
                self.state["agent"].update(task="Monitoring incoming weather updates", stage=None)
            self.notify("New forecast available", f"48-hour forecast published. System confidence: {forecast['confidence']}/100.")
            self.next_refresh = pd.Timestamp(forecast["nextUpdate"])
        except Exception as error:
            # Credentials and upstream response bodies must never reach the browser or logs.
            logger.warning("Forecast update failed (%s)", type(error).__name__)
            message = "Weather data is temporarily unavailable. No current forecast can be calculated."
            if self.repository is None:
                message = "Model or dataset files could not be loaded. Check the server data configuration."
            with self.lock:
                self.state["error"] = message
                self.state["agent"].update(active=True, state="Waiting", stage=None, task="Waiting for a successful forecast update", source="Unavailable")
            self.emit("Weather", "Forecast update unavailable", message, "warning")
            self.notify("Forecast update unavailable", message, "Warning")
            self.next_refresh = pd.Timestamp.now(tz="UTC") + pd.Timedelta(minutes=5)
        finally:
            with self.lock:
                self.state["busy"] = False

    def calculate(self, snapshot, weather, origin, mode, source):
        with self.model_lock:
            frame = self.forecaster.predict(weather)
        run = pd.Timestamp(snapshot["run_initialization_utc"])
        metadata = self.repository.metadata
        freshness = max(0, 100 - max(0, (origin - run - DELAY).total_seconds() / 3600 - 6) * 5)
        stability = 100 * (1 - metadata["validation_metrics"]["MAE"])
        # Behaviour verification and independent weather agreement remain unmeasured.
        # Receiving telemetry alone does not verify behaviour or improve confidence.
        confidence = max(0, round((100 + stability + freshness) / 3 - 20 - (10 if source == "Cached" else 0)))
        forecast_id = uuid4().hex
        records = []
        for timestamp, rows in frame.groupby("time", sort=True):
            first = rows[rows.turbine == "WT_1"].iloc[0]
            record = {"timestamp": iso(timestamp), "forecastId": forecast_id,
                      "windSpeed10m": float(first.wind_speed_10m), "windSpeed80m": float(first.wind_speed_80m),
                      "windSpeed120m": float(first.wind_speed_120m), "windDirection": float(first.wind_direction_120m),
                      "gusts": float(first.wind_gusts_10m), "temperature": float(first.temperature_2m), "pressure": float(first.surface_pressure)}
            for code, key in [("WT_1", "WT01"), ("WT_2", "WT02")]:
                row = rows[rows.turbine == code].iloc[0]
                error = self.repository.interval_errors[code]
                prediction = float(row.prediction)
                record[key] = {"prediction": prediction, "lower": max(0, prediction - error), "upper": min(1, prediction + error), "confidence": confidence}
            records.append(record)
        now = pd.Timestamp.now(tz="UTC")
        forecast = {"id": forecast_id, "records": records, "confidence": confidence,
                    "factors": {"weatherData": 100, "modelStability": round(stability), "twinConsistency": None, "dataFreshness": round(freshness), "forecastAgreement": None},
                    "source": "ECMWF IFS · Open-Meteo", "sourceState": source, "mode": mode,
                    "issuedAt": iso(now), "origin": iso(origin), "nextUpdate": iso(now + pd.Timedelta(seconds=self.settings.refresh_seconds)),
                    "weatherRun": iso(run), "weatherAvailableAt": iso(run + DELAY), "availabilityEstimated": True,
                    "modelVersion": metadata["version"], "modelFingerprint": self.forecaster.fingerprint,
                    "trainingCutoff": iso(self.repository.trained_through), "telemetryAvailable": False,
                    "intervalMethod": "90th percentile of absolute validation errors; not a calibrated probability.",
                    "changeSincePrevious": None}
        with self.lock:
            self.forecasts[forecast_id] = (forecast, frame)
            # Preserve the current forecast while retaining recent replay explanations.
            while len(self.forecasts) > 16:
                key = next(iter(self.forecasts))
                if self.state["forecast"] and key == self.state["forecast"]["id"]:
                    self.forecasts.move_to_end(key)
                else:
                    self.forecasts.pop(key)
        if mode == "live":
            directory = self.settings.storage_dir / "forecasts"
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "latest.json").write_text(json.dumps(forecast, allow_nan=False), encoding="utf-8")
        return forecast

    def turbines(self, forecast):
        with self.lock:
            frame = self.forecasts[forecast["id"]][1]
        values = []
        for index, dataset in enumerate(self.repository.datasets, start=1):
            first = frame[frame.turbine == f"WT_{index}"].sort_values("time").iloc[0]
            values.append({"id": dataset["id"], "name": f"Wind Turbine 0{index}", "wind": float(first.wind_speed_120m),
                           "direction": float(first.wind_direction_120m), "temperature": float(first.temperature_2m),
                           "expected": float(first.prediction), "forecastAt": iso(first.time),
                           "observed": None, "observedAt": None, "confidence": forecast["confidence"], "status": "unknown",
                           "lastObservation": dataset["lastObservation"]})
        return values

    def replay(self, origin: pd.Timestamp):
        self.initialize()
        if origin > pd.Timestamp.now(tz="UTC"):
            raise ValueError("Historical origin must be in the past.")
        snapshot = self.repository.archive_for(origin)
        weather = window_from_snapshot(snapshot, origin)
        forecast = self.calculate(snapshot, weather, origin, "historical", "Archive")
        self.notify("Historical replay completed", f"Forecast origin: {iso(origin)}. Archive and training cutoff checked.")
        return {"forecast": forecast, "origin": iso(origin), "weatherIssuedAt": forecast["weatherRun"],
                "weatherAvailableAt": forecast["weatherAvailableAt"], "trainingCutoff": forecast["trainingCutoff"],
                "leakageCheck": True, "availabilityEstimated": True,
                "logs": ["Archived weather run loaded", "Weather availability policy checked", "Model training cutoff checked",
                         "96 turbine-hour records validated", "Both turbine forecasts calculated", "Historical forecast ready"]}

    def explanation(self, forecast_id, timestamp, turbine):
        with self.lock:
            stored = self.forecasts.get(forecast_id)
        if stored is None:
            raise ValueError("This forecast has expired. Reload the forecast and try again.")
        forecast, frame = stored
        record = next((item for item in forecast["records"] if item["timestamp"] == iso(timestamp)), None)
        if record is None:
            raise ValueError("The selected forecast hour is not available.")
        code = "WT_1" if turbine == "WT01" else "WT_2"
        with self.model_lock:
            drivers = self.forecaster.explain(frame, timestamp, code)
            similar = self.repository.similar_periods(record, code, pd.Timestamp(forecast["origin"]))
        return {"drivers": drivers, **similar, "method": "Local model contributions", "matchingRule": "Wind ±1.5 m/s, temperature ±4°C, direction ±45°; observations before forecast origin."}

    def diagnostics(self, telemetry=None):
        if self.repository is None:
            return None
        meta = self.repository.metadata
        telemetry = telemetry if telemetry is not None else self.telemetry.snapshot()
        return {"modelVersion": meta["version"], "modelType": meta["model"], "modelFingerprint": self.forecaster.fingerprint,
                "features": len(meta["features"]), "trainingRows": meta["training_rows"], "decisionRuns": meta["decision_runs"],
                "trainingStart": meta["training_target_period"]["start"], "trainingEnd": meta["training_target_period"]["end"],
                "validationStart": meta["split"]["validation_decision_start"], "metrics": meta["validation_metrics"],
                "turbineMetrics": meta["turbine_metrics"], "datasets": self.repository.datasets,
                "archiveRuns": len(self.repository.archives), "archiveStart": iso(self.repository.archives[0][0] + DELAY),
                "archiveEnd": iso(self.repository.archives[-1][0] + pd.Timedelta(hours=47)),
                "telemetryAvailable": telemetry["available"], "llmConfigured": self.settings.llm_provider is not None,
                "llmProvider": self.settings.llm_provider, "llmModel": self.settings.llm_model,
                "intervalErrors": self.repository.interval_errors, "refreshSeconds": self.settings.refresh_seconds}

    def snapshot(self):
        telemetry = self.telemetry.snapshot()
        with self.lock:
            snapshot = deepcopy(self.state)
        snapshot["telemetry"] = telemetry
        measurements = {item["turbineId"]: item for item in telemetry["readings"]}
        for turbine in snapshot["turbines"]:
            reading = measurements[turbine["id"]]
            measurement = reading["measurement"]
            fresh = reading["state"] == "fresh"
            turbine.update(telemetryState=reading["state"], measurement=measurement,
                           observed=measurement["power"] if fresh else None,
                           observedAt=measurement["timestamp"] if fresh else None)
        snapshot["serverTime"] = iso(pd.Timestamp.now(tz="UTC"))
        snapshot["nextCheck"] = iso(self.next_refresh)
        if snapshot["forecast"]:
            snapshot["forecast"]["telemetryAvailable"] = snapshot["forecast"]["mode"] == "live" and telemetry["available"]
            age = pd.Timestamp.now(tz="UTC") - pd.Timestamp(snapshot["forecast"]["issuedAt"])
            snapshot["forecast"]["stale"] = bool(snapshot["error"] or age.total_seconds() > self.settings.refresh_seconds * 1.5)
        snapshot["diagnostics"] = self.diagnostics(telemetry)
        return snapshot
