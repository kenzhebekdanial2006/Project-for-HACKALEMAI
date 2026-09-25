import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class LiveApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.forecast_path = Path(self.temporary.name) / 'forecast.json'
        self.analysis_path = Path(self.temporary.name) / 'analysis.json'
        self.forecast = {'forecast_count': 96, 'power_model': 'catboost_weather_v2'}
        self.analysis = {
            'agent_model': 'test-model',
            'analysis': {'summary': 'Test summary', 'recalculate': False},
        }
        for name, path in [('LIVE_JSON', self.forecast_path), ('ANALYSIS_JSON', self.analysis_path)]:
            patcher = patch.object(main, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(main.app)

    def test_full_pipeline_runs_forecast_before_analysis(self):
        order = []

        def forecast():
            order.append('forecast')
            self.forecast_path.write_text(json.dumps(self.forecast), encoding='utf-8')

        def analyze():
            self.assertTrue(self.forecast_path.exists())
            order.append('analysis')
            return self.analysis

        with patch.object(main, 'generate_live_forecast', side_effect=forecast), patch.object(
            main, 'analyze_live_forecast', side_effect=analyze
        ):
            response = self.client.post('/api/recalculate')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order, ['forecast', 'analysis'])
        self.assertEqual(response.json()['agent'], 'test-model')
        self.assertEqual(response.json()['forecast_count'], 96)
        self.assertFalse(response.json()['recalculate'])

    def test_analysis_only_does_not_generate_weather(self):
        with patch.object(main, 'generate_live_forecast') as forecast, patch.object(
            main, 'analyze_live_forecast', return_value=self.analysis
        ) as analyze:
            response = self.client.post('/api/analysis/recalculate')
        self.assertEqual(response.json(), self.analysis)
        forecast.assert_not_called()
        analyze.assert_called_once_with()

    def test_forecast_failure_stops_pipeline(self):
        with patch.object(main, 'generate_live_forecast', side_effect=RuntimeError('Weather unavailable')), patch.object(
            main, 'analyze_live_forecast'
        ) as analyze:
            self.assertEqual(self.client.post('/api/recalculate').status_code, 500)
        analyze.assert_not_called()

    def test_analysis_failure_returns_error(self):
        with patch.object(main, 'analyze_live_forecast', side_effect=RuntimeError('API unavailable')):
            self.assertEqual(self.client.post('/api/analysis/recalculate').status_code, 500)
            with patch.object(main, 'generate_live_forecast'):
                self.assertEqual(self.client.post('/api/recalculate').status_code, 500)

    def test_saved_analysis_and_missing_or_invalid_file(self):
        self.assertEqual(self.client.get('/api/analysis/latest').status_code, 404)
        self.analysis_path.write_text(json.dumps(self.analysis), encoding='utf-8')
        self.assertEqual(self.client.get('/api/analysis/latest').json(), self.analysis)
        for invalid in ('{broken', '[]'):
            self.analysis_path.write_text(invalid, encoding='utf-8')
            self.assertEqual(self.client.get('/api/analysis/latest').status_code, 500)


if __name__ == '__main__':
    unittest.main()
