from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.windops.api.runtime import Runtime
from backend.windops.core.config import settings
from backend.windops.data.telemetry import TelemetryBatch, TelemetryStore, MAX_FILE_BYTES
from backend.windops.agent.copilot import answer_question


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = replace(settings, storage_dir=Path(self.temporary.name), telemetry_file=None,
                                telemetry_key="test-ingestion-key", telemetry_max_age_seconds=1200,
                                openai_key="", nvidia_key="", nvidia_model="")
        self.now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
        self.store = TelemetryStore(self.settings)

    def reading(self, turbine="WT-01", power=.42, when=None):
        return {"turbineId": turbine, "power": power,
                "timestamp": (when or self.now - timedelta(minutes=2)).isoformat(), "windSpeed": 7.2}

    def ingest(self, rows, store=None, now=None):
        return (store or self.store).ingest(TelemetryBatch.model_validate({"readings": rows}), now or self.now)

    def test_unconfigured_and_waiting_are_different(self):
        self.assertEqual(self.store.snapshot(self.now)["status"], "waiting")
        unconfigured = TelemetryStore(replace(self.settings, telemetry_key=""))
        self.assertEqual(unconfigured.snapshot(self.now)["status"], "not_configured")
        self.assertFalse(unconfigured.snapshot(self.now)["available"])

    def test_partial_then_both_turbines_and_restart_preserve_zero_power(self):
        result = self.ingest([self.reading(power=0)])
        self.assertEqual(result["telemetry"]["status"], "partial")
        self.assertFalse(result["telemetry"]["available"])
        result = self.ingest([self.reading("WT-02", power=.55)])
        self.assertEqual(result["telemetry"]["status"], "connected")
        self.assertEqual(result["telemetry"]["freshCount"], 2)
        restored = TelemetryStore(self.settings).snapshot(self.now)
        self.assertTrue(restored["available"])
        self.assertEqual(restored["readings"][0]["measurement"]["power"], 0)

    def test_old_and_duplicate_packets_never_make_stale_values_fresh(self):
        newest = self.reading(when=self.now)
        self.ingest([newest])
        later = self.now + timedelta(minutes=21)
        result = self.ingest([newest, self.reading(when=self.now - timedelta(days=1))], now=later)
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["ignored"], 2)
        row = result["telemetry"]["readings"][0]
        self.assertEqual(row["state"], "stale")
        self.assertEqual(row["measurement"]["timestamp"], "2026-09-23T12:00:00Z")
        self.assertFalse(result["telemetry"]["available"])

    def test_archive_remains_stale_and_timezone_is_normalized(self):
        self.ingest([self.reading(when=datetime(2026, 1, 31, 18, 0, tzinfo=timezone.utc))])
        self.assertEqual(self.store.snapshot(self.now)["status"], "stale")
        row = self.reading()
        row["timestamp"] = "2026-09-23T16:59:00+05:00"
        result = self.ingest([row])
        self.assertEqual(result["telemetry"]["readings"][0]["measurement"]["timestamp"], "2026-09-23T11:59:00Z")

    def test_invalid_values_units_and_unknown_turbines_are_rejected_atomically(self):
        for changes in ({"power": 42}, {"power": -.01}, {"power": True}, {"power": float("nan")},
                        {"power": float("inf")}, {"timestamp": "2026-09-23T11:59:00"},
                        {"timestamp": 12345}, {"turbineId": "WT-03"}, {"windSpeed": -2},
                        {"powerKw": 400}, {"windDirection": 361}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.ingest([self.reading(), {**self.reading("WT-02"), **changes}])
        self.assertFalse(self.store.path.exists())
        with self.assertRaisesRegex(ValueError, "Future measurements"):
            self.ingest([self.reading(), self.reading("WT-02", when=self.now + timedelta(seconds=1))])
        self.assertFalse(self.store.path.exists())

    def test_csv_source_updates_without_restart_and_invalid_file_is_not_current(self):
        path = Path(self.temporary.name) / "measurements.csv"
        path.write_text("turbineId,timestamp,power,windSpeed\nWT-01,2026-09-23T11:59:00Z,0.21,7.2\n", encoding="utf-8")
        store = TelemetryStore(replace(self.settings, telemetry_file=path))
        self.assertEqual(store.snapshot(self.now)["status"], "partial")
        path.write_text("turbineId,timestamp,power,windSpeed\nWT-01,2026-09-23T12:00:00Z,0.5,8.1\nWT-02,2026-09-23T12:00:00Z,0.55,\n", encoding="utf-8")
        self.assertTrue(store.snapshot(self.now)["available"])
        self.assertIsNone(store.snapshot(self.now)["readings"][1]["measurement"]["windSpeed"])
        with self.assertRaisesRegex(ValueError, "file is configured"):
            self.ingest([self.reading()], store)
        path.write_text("turbineId,timestamp,power\nWT-01,bad,banana\n", encoding="utf-8")
        result = store.snapshot(self.now)
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["available"])
        self.assertEqual(result["readings"][0]["measurement"]["power"], .5)
        self.assertEqual(result["readings"][0]["state"], "unavailable")
        self.assertNotIn(str(path), json.dumps(result))

    def test_missing_oversized_and_future_file_are_not_accepted(self):
        path = Path(self.temporary.name) / "measurements.json"
        store = TelemetryStore(replace(self.settings, telemetry_file=path))
        self.assertEqual(store.snapshot(self.now)["status"], "waiting")
        path.write_text(json.dumps({"readings": [self.reading(when=self.now + timedelta(hours=1))]}), encoding="utf-8")
        self.assertEqual(store.snapshot(self.now)["status"], "error")
        path.write_text(" " * (MAX_FILE_BYTES + 1), encoding="utf-8")
        self.assertEqual(store.snapshot(self.now)["status"], "error")
        path.write_text(json.dumps({"readings": [self.reading()]}), encoding="utf-8")
        self.assertEqual(store.snapshot(self.now)["status"], "partial")
        path.unlink()
        self.assertEqual(store.snapshot(self.now)["status"], "error")

    def test_unchanged_file_recovers_after_transient_access_failure(self):
        self.ingest([self.reading(), self.reading("WT-02")])
        with patch.object(Path, "stat", side_effect=PermissionError("temporarily unavailable")):
            snapshot = self.store.snapshot(self.now)
        self.assertEqual(snapshot["status"], "error")
        self.assertFalse(snapshot["available"])
        recovered = self.store.snapshot(self.now)
        self.assertEqual(recovered["status"], "connected")
        self.assertTrue(recovered["available"])
        self.assertIsNone(recovered["error"])

    def test_failed_persistence_does_not_publish_unstored_values(self):
        self.ingest([self.reading()])
        with patch.object(Path, "replace", side_effect=OSError("disk unavailable")), self.assertRaises(OSError):
            self.ingest([self.reading(power=.8, when=self.now)])
        self.assertEqual(self.store.snapshot(self.now)["readings"][0]["measurement"]["power"], .42)

    def test_snapshot_uses_actual_power_without_claiming_healthy_operation(self):
        runtime = Runtime(self.settings)
        runtime.telemetry = self.store
        self.ingest([self.reading(power=0), self.reading("WT-02", power=.54)])
        runtime.state["forecast"] = {"id": "test-forecast", "issuedAt": self.now.isoformat(),
                                     "mode": "live", "confidence": 74, "telemetryAvailable": False}
        runtime.state["turbines"] = [{"id": turbine, "expected": .8, "status": "unknown", "observed": None,
                                       "observedAt": None} for turbine in ("WT-01", "WT-02")]
        with patch.object(self.store, "_now", return_value=self.now):
            snapshot = runtime.snapshot()
        self.assertTrue(snapshot["forecast"]["telemetryAvailable"])
        self.assertEqual(snapshot["forecast"]["confidence"], 74)
        self.assertEqual([row["observed"] for row in snapshot["turbines"]], [0, .54])
        self.assertTrue(all(row["status"] == "unknown" for row in snapshot["turbines"]))
        runtime.state["forecast"]["mode"] = "historical"
        with patch.object(self.store, "_now", return_value=self.now):
            self.assertFalse(runtime.snapshot()["forecast"]["telemetryAvailable"])
        with patch.object(self.store, "_now", return_value=self.now + timedelta(minutes=30)):
            snapshot = runtime.snapshot()
        self.assertTrue(all(row["observed"] is None for row in snapshot["turbines"]))
        self.assertTrue(all(row["telemetryState"] == "stale" for row in snapshot["turbines"]))

    def test_api_requires_dedicated_key_and_reports_validation_errors(self):
        from backend.windops.api import app as api
        runtime = Runtime(self.settings)
        now = datetime.now(timezone.utc) - timedelta(seconds=1)
        body = {"readings": [self.reading(when=now), self.reading("WT-02", when=now)]}
        with patch.object(api, "runtime", runtime):
            client = TestClient(api.app)
            self.assertEqual(client.post("/api/telemetry", json=body).status_code, 401)
            self.assertEqual(client.post("/api/telemetry", json=body, headers={"X-Telemetry-Key": "wrong"}).status_code, 401)
            response = client.post("/api/telemetry", json=body, headers={"X-Telemetry-Key": self.settings.telemetry_key})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["telemetry"]["available"])
            self.assertEqual(client.get("/api/telemetry").json()["freshCount"], 2)
            self.assertNotIn(self.settings.telemetry_key, client.get("/api/operations").text)
            invalid = deepcopy(body)
            invalid["readings"][1]["power"] = 54
            self.assertEqual(client.post("/api/telemetry", json=invalid,
                                       headers={"X-Telemetry-Key": self.settings.telemetry_key}).status_code, 422)
            invalid["readings"][1]["power"] = float("nan")
            self.assertEqual(client.post("/api/telemetry", content=json.dumps(invalid),
                                       headers={"X-Telemetry-Key": self.settings.telemetry_key,
                                                "Content-Type": "application/json"}).status_code, 422)
        with patch.object(api, "runtime", Runtime(replace(self.settings, telemetry_key=""))):
            self.assertEqual(TestClient(api.app).post("/api/telemetry", json=body).status_code, 503)
        file_settings = replace(self.settings, telemetry_file=Path(self.temporary.name) / "incoming.json", telemetry_key="")
        with patch.object(api, "runtime", Runtime(file_settings)):
            self.assertEqual(TestClient(api.app).post("/api/telemetry", json=body).status_code, 409)

    def test_copilot_reports_available_measurements_and_does_not_invent_missing_ones(self):
        record = {"timestamp": "2026-09-23T13:00:00Z", "windSpeed120m": 8,
                  "WT01": {"prediction": .6}, "WT02": {"prediction": .63}}
        forecast = {"id": "forecast", "records": [record], "confidence": 74}
        turbines = [{"id": "WT-01", "observed": 0, "observedAt": "2026-09-23T12:00:00Z"},
                    {"id": "WT-02", "observed": None, "observedAt": None}]
        for question in ("Compare turbines", "Текущие показания", "Ағымдағы қуат"):
            answer = answer_question(question, forecast, self.settings, turbines=turbines)
            self.assertIn("WT-01 0% at 2026-09-23T12:00:00Z", answer["answer"])
            self.assertIn("WT-02 Unavailable", answer["answer"])
            self.assertIn("does not confirm normal operation", answer["answer"])
            self.assertIn("Current turbine readings", answer["references"])
        for turbine in turbines:
            turbine.update(observed=None, observedAt=None, measurement={"power": .42})
        answer = answer_question("Compare turbines", forecast, self.settings, turbines=turbines)
        self.assertIn("out of date or unavailable", answer["answer"])
        self.assertNotIn("not connected", answer["answer"])


if __name__ == "__main__":
    unittest.main()
