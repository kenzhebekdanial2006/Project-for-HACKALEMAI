from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json

from task import ai_agent


class StandaloneAgentTests(unittest.TestCase):
    def forecast(self):
        now = datetime.now(timezone.utc)
        origin = now.replace(minute=0, second=0, microsecond=0)
        return {
            "id": "published-forecast", "mode": "live", "issuedAt": now.isoformat(),
            "source": "ECMWF", "weatherRun": origin.isoformat(), "modelVersion": "weather_v2",
            "records": [{"timestamp": (origin + timedelta(hours=h)).isoformat(),
                         "windSpeed120m": 8, "gusts": 12, "temperature": 18, "windDirection": 240,
                         "WT01": {"prediction": 0.123456789}, "WT02": {"prediction": 0.5}}
                        for h in range(1, 49)],
        }

    def test_published_values_and_timestamps_are_preserved(self):
        source = self.forecast()
        result = ai_agent.adapt_backend_forecast(source)
        self.assertTrue(ai_agent.validate_forecast(result)["valid"])
        self.assertEqual(len(result["forecasts"]), 96)
        for index, row in enumerate(result["forecasts"]):
            original = source["records"][index // 2]
            self.assertEqual(row["time"], original["timestamp"])
            self.assertEqual(row["predicted_power"], original["WT01" if index % 2 == 0 else "WT02"]["prediction"])
            self.assertEqual(row["forecast_horizon_hour"], index // 2 + 1)

    def test_stale_archived_and_incomplete_forecasts_are_rejected(self):
        for kind in ("stale", "archive", "missing", "duplicate"):
            forecast = self.forecast()
            if kind == "stale":
                forecast["issuedAt"] = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            elif kind == "archive":
                forecast["mode"] = "historical"
            elif kind == "missing":
                forecast["records"].pop()
            else:
                forecast["records"][1]["timestamp"] = forecast["records"][0]["timestamp"]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                ai_agent.adapt_backend_forecast(forecast)

    def test_backend_snapshot_is_used_when_legacy_file_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = Path(directory) / "latest.json"
            backend.write_text(json.dumps(self.forecast()), encoding="utf-8")
            with patch.object(ai_agent, "FORECAST_PATH", Path(directory) / "missing.json"), \
                    patch.object(ai_agent, "BACKEND_FORECAST_PATH", backend):
                self.assertEqual(ai_agent.load_forecast()["forecast_id"], "published-forecast")

    def test_invalid_power_prevents_model_call(self):
        forecast = ai_agent.adapt_backend_forecast(self.forecast())
        forecast["forecasts"][0]["predicted_power"] = 5
        with patch.object(ai_agent, "load_forecast", return_value=forecast), \
                patch.object(ai_agent, "call_openai_agent") as call:
            with self.assertRaises(ValueError):
                ai_agent.analyze_live_forecast()
            call.assert_not_called()
