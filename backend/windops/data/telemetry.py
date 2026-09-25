"""Validated measured power, independent from weather forecasts and training data."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import threading
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

TURBINES = ("WT-01", "WT-02")
MAX_FILE_BYTES = 2 * 1024 * 1024


class TelemetryReading(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    turbineId: Literal["WT-01", "WT-02"]
    timestamp: AwareDatetime
    power: float = Field(ge=0, le=1, description="Measured power / rated power, from 0 to 1; not kW or percent.")
    windSpeed: float | None = Field(default=None, ge=0, le=120, description="Measured wind speed in m/s.")
    windDirection: float | None = Field(default=None, ge=0, le=360)
    temperature: float | None = Field(default=None, ge=-80, le=70)

    @field_validator("power", "windSpeed", "windDirection", "temperature", mode="before")
    @classmethod
    def reject_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError("A measurement must be a number.")
        return value

    @field_validator("timestamp", mode="before")
    @classmethod
    def require_datetime(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Use an ISO 8601 timestamp with a timezone.")
        return value

    @field_validator("timestamp")
    @classmethod
    def use_utc(cls, value):
        return value.astimezone(timezone.utc)


class TelemetryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    readings: list[TelemetryReading] = Field(min_length=1, max_length=2000)


class TelemetryStore:
    """Keep the latest measurement per turbine; never move measurement timestamps."""

    def __init__(self, settings):
        self.path = settings.telemetry_file or settings.storage_dir / "telemetry/latest.json"
        self.file_mode = settings.telemetry_file is not None
        self.api_enabled = bool(settings.telemetry_key) and not self.file_mode
        self.max_age = settings.telemetry_max_age_seconds
        self.lock = threading.RLock()
        self.readings: dict[str, TelemetryReading] = {}
        self.signature = None
        self.error = None

    @staticmethod
    def _now(now):
        return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    @staticmethod
    def _validate_time(readings, now):
        if any(reading.timestamp > now for reading in readings):
            raise ValueError("Future measurements are not accepted. Use the actual measurement time with its timezone.")

    def _merge(self, readings):
        latest = dict(self.readings)
        accepted = 0
        for reading in sorted(readings, key=lambda item: item.timestamp):
            previous = latest.get(reading.turbineId)
            if previous is None or reading.timestamp > previous.timestamp:
                latest[reading.turbineId] = reading
                accepted += 1
        return latest, accepted

    def _reload(self, now):
        try:
            stat = self.path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            if signature == self.signature:
                return
            if stat.st_size > MAX_FILE_BYTES:
                raise ValueError("Telemetry file exceeds the supported snapshot size.")
            with self.path.open("r", encoding="utf-8-sig", newline="") as stream:
                content = stream.read(MAX_FILE_BYTES + 1)
            if len(content.encode("utf-8")) > MAX_FILE_BYTES:
                raise ValueError("Telemetry file exceeds the supported snapshot size.")
            if self.path.suffix.lower() == ".csv":
                rows = [{key: value for key, value in row.items() if value != ""}
                        for row in csv.DictReader(io.StringIO(content))]
                batch = TelemetryBatch.model_validate({"readings": rows})
            else:
                batch = TelemetryBatch.model_validate_json(content)
            self._validate_time(batch.readings, now)
            self.readings, _ = self._merge(batch.readings)
            self.signature, self.error = signature, None
        except FileNotFoundError:
            self.signature = None
            self.error = "The telemetry file is unavailable." if self.readings else None
        except (OSError, ValueError, TypeError):
            # Retry validation after a transient read failure even if the file
            # has not changed since the last successful snapshot.
            self.signature = None
            # Do not leak file paths, content, or exception traces to the operator.
            self.error = "Turbine readings could not be validated. Check timestamps, units and file format."

    def ingest(self, batch: TelemetryBatch, now=None):
        if self.file_mode:
            raise ValueError("A telemetry file is configured. Update that file to publish measurements.")
        now = self._now(now)
        self._validate_time(batch.readings, now)
        with self.lock:
            self._reload(now)
            latest, accepted = self._merge(batch.readings)
            payload = {"readings": [reading.model_dump(mode="json") for reading in latest.values()]}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                                 suffix=".tmp", delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(payload, stream, allow_nan=False)
                temporary.replace(self.path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            self.readings, self.error = latest, None
            stat = self.path.stat()
            self.signature = (stat.st_mtime_ns, stat.st_size)
            return {"accepted": accepted, "ignored": len(batch.readings) - accepted,
                    "telemetry": self.snapshot(now)}

    def snapshot(self, now=None):
        now = self._now(now)
        with self.lock:
            self._reload(now)
            configured = self.file_mode or self.api_enabled or bool(self.readings)
            rows = []
            for turbine in TURBINES:
                reading = self.readings.get(turbine)
                age = (now - reading.timestamp).total_seconds() if reading else None
                fresh = reading is not None and 0 <= age <= self.max_age and not self.error
                rows.append({"turbineId": turbine,
                             "state": "unavailable" if self.error else "fresh" if fresh else "stale" if reading else "missing",
                             "ageSeconds": round(age) if age is not None else None,
                             "measurement": reading.model_dump(mode="json") if reading else None})
            fresh_count = sum(row["state"] == "fresh" for row in rows)
            status = ("error" if self.error else "connected" if fresh_count == 2 else "partial" if fresh_count else
                      "stale" if self.readings else "waiting" if configured else "not_configured")
            return {"status": status, "available": fresh_count == 2, "freshCount": fresh_count,
                    "source": ("CSV file" if self.path.suffix.lower() == ".csv" else "JSON file") if self.file_mode else "Telemetry API",
                    "maxAgeSeconds": self.max_age, "apiEnabled": self.api_enabled,
                    "fileConfigured": self.file_mode, "error": self.error, "readings": rows}
