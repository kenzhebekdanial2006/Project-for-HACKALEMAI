from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.windops.core.config import settings
from backend.windops.weather.runs import window_from_snapshot
from backend.windops.api.runtime import Runtime
from backend.windops.agent.copilot import answer_question


@unittest.skipUnless((settings.task_dir / 'models/catboost_weather.cbm').exists(), 'Local task artifacts are required')
class RealArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.settings = replace(settings, storage_dir=Path(cls.temporary.name), openai_key='', nvidia_key='', nvidia_model='')
        cls.runtime = Runtime(cls.settings)
        cls.runtime.initialize()
        cls.repository = cls.runtime.repository
        cls.model = cls.runtime.forecaster
        cls.origin = pd.Timestamp('2026-02-03T08:00:00Z')
        cls.replay = cls.runtime.replay(cls.origin)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_predictions_match_original_research_export(self):
        origin = pd.Timestamp('2026-01-31T18:50:00Z')
        # Numeric parity is independent of the stricter replay cutoff: the full
        # final hourly training bucket must have elapsed before replay is allowed.
        snapshot = json.loads((settings.task_dir / 'weather_backtest/20260131/response.json').read_text(encoding='utf-8'))
        actual = self.model.predict(window_from_snapshot(snapshot, origin))
        original = pd.read_csv(settings.task_dir / 'predictions/forecast_february.csv')
        original['decision_time_utc'] = pd.to_datetime(original.decision_time_utc, utc=True)
        expected = original[original.decision_time_utc == origin].copy()
        expected['time'] = pd.to_datetime(expected.timestamp).dt.tz_localize('Asia/Almaty').dt.tz_convert('UTC')
        merged = actual.merge(expected[['time', 'turbine', 'predicted_power']], on=['time', 'turbine'], validate='one_to_one')
        self.assertEqual(len(merged), 96)
        np.testing.assert_allclose(merged.prediction, merged.predicted_power, atol=1e-12, rtol=0)

    def test_archive_checks_time_and_training_cutoff(self):
        replay = self.replay
        self.assertTrue(replay['leakageCheck'])
        self.assertTrue(replay['availabilityEstimated'])
        self.assertLessEqual(pd.Timestamp(replay['weatherAvailableAt']), self.origin)
        self.assertLess(pd.Timestamp(replay['trainingCutoff']), self.origin)
        self.assertEqual(replay['weatherIssuedAt'], '2026-02-02T12:00:00Z')
        with self.assertRaisesRegex(ValueError, 'training cutoff'):
            self.runtime.replay(pd.Timestamp('2026-01-30T08:00:00Z'))
        with self.assertRaisesRegex(ValueError, 'training cutoff'):
            self.runtime.replay(pd.Timestamp('2026-01-31T18:30:00Z'))
        self.assertEqual(replay['trainingCutoff'], '2026-01-31T19:00:00Z')
        with self.assertRaisesRegex(ValueError, 'covers the selected date'):
            self.runtime.replay(pd.Timestamp('2026-05-03T08:00:00Z'))

    def test_all_48_hours_are_complete_and_bounded(self):
        forecast = self.replay['forecast']
        self.assertEqual(len(forecast['records']), 48)
        timestamps = pd.DatetimeIndex([row['timestamp'] for row in forecast['records']])
        self.assertTrue(timestamps.equals(pd.date_range('2026-02-03T09:00Z', periods=48, freq='h')))
        for row in forecast['records']:
            for turbine in ['WT01', 'WT02']:
                power = row[turbine]
                self.assertLessEqual(0, power['lower'])
                self.assertLessEqual(power['lower'], power['prediction'])
                self.assertLessEqual(power['prediction'], power['upper'])
                self.assertLessEqual(power['upper'], 1)
        self.assertIsNone(forecast['factors']['twinConsistency'])
        self.assertIsNone(forecast['factors']['forecastAgreement'])

    def test_weather_validation_rejects_wrong_units_missing_hours_and_future_runs(self):
        source = self.repository.archive_for(self.origin)
        broken = deepcopy(source)
        broken['response'][0]['hourly_units']['wind_speed_120m'] = 'km/h'
        with self.assertRaisesRegex(ValueError, 'metres per second'):
            window_from_snapshot(broken, self.origin)
        broken = deepcopy(source)
        # Remove the complete row for one target hour.
        target = int((self.origin.floor('h') + pd.Timedelta(hours=1)).timestamp())
        hour_index = broken['response'][0]['hourly']['time'].index(target)
        for values in broken['response'][0]['hourly'].values():
            values.pop(hour_index)
        with self.assertRaisesRegex(ValueError, '48 requested hours'):
            window_from_snapshot(broken, self.origin)
        with self.assertRaisesRegex(ValueError, 'not available'):
            window_from_snapshot(source, pd.Timestamp(source['run_initialization_utc']))

    def test_no_archived_measurement_is_presented_as_live(self):
        turbines = self.runtime.turbines(self.replay['forecast'])
        for turbine in turbines:
            self.assertIsNone(turbine['observed'])
            self.assertIsNone(turbine['observedAt'])
            self.assertEqual(turbine['status'], 'unknown')
            self.assertEqual(turbine['lastObservation']['timestamp'], '2026-01-31T18:00:00Z')

    def test_diagnostics_use_weather_model_metrics_and_real_record_counts(self):
        data = self.runtime.diagnostics()
        self.assertEqual([row['records'] for row in data['datasets']], [142360, 149499])
        self.assertEqual(data['metrics']['MAE'], self.repository.metadata['validation_metrics']['MAE'])
        self.assertAlmostEqual(data['metrics']['MAE'], .1828468046338307)
        self.assertEqual(data['features'], 25)

    def test_explanations_and_similar_periods_are_from_actual_artifacts(self):
        forecast = self.replay['forecast']
        row = forecast['records'][8]
        explanation = self.runtime.explanation(forecast['id'], row['timestamp'], 'WT01')
        self.assertTrue(explanation['drivers'])
        self.assertTrue(any(driver['contribution'] != 0 for driver in explanation['drivers']))
        for period in explanation['periods']:
            self.assertLess(pd.Timestamp(period['timestamp']), self.origin)
            records = self.repository.hourly
            actual = records[(records.turbine == 'WT_1') & (records.time_utc == pd.Timestamp(period['timestamp']))]
            self.assertEqual(len(actual), 1)
            self.assertAlmostEqual(period['power'], float(actual.iloc[0].power))

    def test_refresh_failure_retains_last_forecast_and_marks_it_stale(self):
        runtime = Runtime(self.settings)
        runtime.repository, runtime.forecaster = self.repository, self.model
        runtime.state['forecast'] = deepcopy(self.replay['forecast'])
        with patch('backend.windops.api.runtime.fetch_live', side_effect=RuntimeError('upstream unavailable')):
            runtime.refresh()
        snapshot = runtime.snapshot()
        self.assertEqual(snapshot['forecast']['id'], self.replay['forecast']['id'])
        self.assertTrue(snapshot['forecast']['stale'])
        self.assertEqual(snapshot['agent']['source'], 'Unavailable')
        self.assertIsNotNone(snapshot['error'])
        self.assertNotIn('upstream unavailable', json.dumps(snapshot))

    def test_api_replay_validation_and_explanation_contract(self):
        from backend.windops.api import app as api
        # No network startup in this test; a fully initialized runtime uses real local artifacts.
        with patch.object(api, 'runtime', self.runtime):
            client = TestClient(api.app)
            response = client.post('/api/replay', json={'date': '2026-02-03', 'time': '08:00'})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            explanation = client.get('/api/forecast/explanation', params={'forecast_id': data['forecast']['id'], 'timestamp': data['forecast']['records'][0]['timestamp'], 'turbine': 'WT02'})
            self.assertEqual(explanation.status_code, 200)
            self.assertEqual(client.post('/api/replay', json={'date': '2026-02-30', 'time': '08:00'}).status_code, 422)
            self.assertEqual(client.post('/api/replay', json={'date': '2026-01-20', 'time': '08:00'}).status_code, 422)

    def test_copilot_uses_real_predictions_without_inventing_telemetry(self):
        forecast = self.replay['forecast']
        for question in ['Compare turbines', 'Есть ли аномалии?', 'Ауытқулар бар ма?']:
            answer = answer_question(question, forecast, self.settings)
            self.assertIn('telemetry is not connected', answer['answer'])
            self.assertEqual(answer['provider'], 'Data analysis')
        for question in ['Why is confidence lower?', 'Почему снизилась надёжность?', 'Болжам сенімділігі неге төмендеді?']:
            self.assertIn(f"{forecast['confidence']}/100", answer_question(question, forecast, self.settings)['answer'])


if __name__ == '__main__':
    unittest.main()
