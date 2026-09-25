from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from openai import APIConnectionError, APIStatusError, APITimeoutError

from backend.windops.agent.copilot import answer_question
from backend.windops.agent.language_model import FALLBACK_NOTICE
from backend.windops.core.config import settings


class CopilotTests(unittest.TestCase):
    def setUp(self):
        self.settings = replace(settings, openai_key='test-openai-key', openai_model='gpt-5.4-mini',
                                nvidia_key='', nvidia_model='')
        self.forecast = {'id': 'forecast-a', 'modelVersion': 'weather_v2', 'confidence': 71,
            'stale': False, 'telemetryAvailable': False, 'records': [
                {'timestamp': '2026-09-23T13:00:00Z', 'windSpeed120m': 6.0,
                 'WT01': {'prediction': .25}, 'WT02': {'prediction': .3}},
                {'timestamp': '2026-09-23T14:00:00Z', 'windSpeed120m': 9.0,
                 'WT01': {'prediction': .7}, 'WT02': {'prediction': .65}}]}
        self.factory = self.enterContext(patch('backend.windops.agent.language_model.OpenAI'))
        self.client = self.factory.return_value.__enter__.return_value
        self.client.responses.create.return_value = SimpleNamespace(status='completed', output_text='Forecast answer.')

    def test_openai_uses_responses_and_actual_facts_without_credentials(self):
        history = [{'role': 'user', 'content': 'Compare turbines'},
                   {'role': 'assistant', 'content': 'Earlier answer'}]
        diagnostics = {'metrics': {'MAE': .18}, 'features': 25, 'private_key': 'must-stay-private'}
        result = answer_question('What about confidence?', self.forecast, self.settings, 'kk',
                                 history=history, diagnostics=diagnostics)
        self.assertEqual(result['provider'], 'OpenAI')
        self.assertEqual(result['model'], 'gpt-5.4-mini')
        self.assertEqual(result['forecastId'], 'forecast-a')
        self.assertFalse(result['fallback'])
        self.assertIsNone(result['notice'])
        options = self.client.responses.create.call_args.kwargs
        self.assertFalse(options['store'])
        self.assertEqual(options['input'][:2], history)
        self.assertIn('Respond in Kazakh', options['instructions'])
        self.assertEqual(self.factory.call_args.kwargs['base_url'], 'https://api.openai.com/v1')
        self.assertEqual(self.factory.call_args.kwargs['max_retries'], 0)
        facts = json.loads(options['input'][-1]['content'])['currentFacts']
        self.assertEqual(facts['forecast']['records'], self.forecast['records'])
        self.assertEqual(facts['diagnostics']['metrics']['MAE'], .18)
        self.assertNotIn('must-stay-private', json.dumps(options))
        self.assertNotIn('test-openai-key', json.dumps(options))

    def test_partial_current_measurements_reach_model_with_timestamps(self):
        turbines = [{'id': 'WT-01', 'observed': 0, 'observedAt': '2026-09-23T12:58:00Z'},
                    {'id': 'WT-02', 'observed': None, 'observedAt': None}]
        result = answer_question('Compare turbines', self.forecast, self.settings, turbines=turbines)
        facts = json.loads(self.client.responses.create.call_args.kwargs['input'][-1]['content'])['currentFacts']
        self.assertEqual(facts['turbines'], turbines)
        self.assertIn('Current turbine readings', result['references'])
        self.assertEqual(len(result['references']), len(set(result['references'])))

    def test_status_errors_return_honest_fallback_without_raw_error_details(self):
        for status, reason in [(401, 'authentication'), (403, 'authentication'), (429, 'rate_limit'), (503, 'unavailable')]:
            with self.subTest(status=status):
                response = httpx.Response(status, request=httpx.Request('POST', 'https://api.openai.com/v1/responses'))
                self.client.responses.create.side_effect = APIStatusError('must-stay-private', response=response, body={})
                result = answer_question('When is the peak?', self.forecast, self.settings)
                self.assertEqual(result['provider'], 'Data analysis')
                self.assertEqual(result['fallbackReason'], reason)
                self.assertEqual(result['notice'], FALLBACK_NOTICE)
                self.assertIn('70%', result['answer'])
                self.assertNotIn('must-stay-private', json.dumps(result))

    def test_connection_and_timeout_failures_keep_data_answers(self):
        request = httpx.Request('POST', 'https://api.openai.com/v1/responses')
        for error, reason in [(APITimeoutError(request=request), 'timeout'),
                              (APIConnectionError(request=request), 'unavailable')]:
            with self.subTest(reason=reason):
                self.client.responses.create.side_effect = error
                result = answer_question('When is the peak?', self.forecast, self.settings)
                self.assertTrue(result['fallback'])
                self.assertEqual(result['fallbackReason'], reason)

    def test_empty_and_incomplete_generations_are_not_presented_as_success(self):
        for status, answer in [('completed', ''), ('completed', '   '), ('incomplete', 'Partial answer')]:
            with self.subTest(status=status, answer=answer):
                self.client.responses.create.return_value = SimpleNamespace(status=status, output_text=answer)
                result = answer_question('When is the peak?', self.forecast, self.settings)
                self.assertEqual(result['provider'], 'Data analysis')
                self.assertEqual(result['fallbackReason'], 'incomplete_response')

    def test_no_configured_provider_does_not_make_external_requests(self):
        result = answer_question('Compare turbines', self.forecast, replace(self.settings, openai_key=''))
        self.assertEqual(result['provider'], 'Data analysis')
        self.assertFalse(result['fallback'])
        self.factory.assert_not_called()

    def test_nvidia_remains_an_explicit_alternative(self):
        configured = replace(self.settings, openai_key='', nvidia_key='test-nvidia-key', nvidia_model='test-model')
        with patch('backend.windops.agent.language_model.requests.post') as request:
            request.return_value.json.return_value = {'choices': [{'message': {'content': 'NVIDIA answer'}}]}
            result = answer_question('When is the peak?', self.forecast, configured)
        self.assertEqual(result['provider'], 'NVIDIA')
        self.factory.assert_not_called()

    def test_config_repr_hides_credentials(self):
        configured = replace(self.settings, nvidia_key='test-nvidia-key', telemetry_key='test-telemetry-key')
        for secret in ['test-openai-key', 'test-nvidia-key', 'test-telemetry-key']:
            self.assertNotIn(secret, repr(configured))


class CopilotApiTests(unittest.TestCase):
    def setUp(self):
        from backend.windops.api import app as api
        self.api = api
        self.snapshot = {'forecast': {'id': 'current'}, 'turbines': [], 'diagnostics': {'features': 25}}
        runtime = SimpleNamespace(settings=replace(settings, openai_key='', nvidia_key=''),
                                  snapshot=lambda: self.snapshot)
        self.enterContext(patch.object(api, 'runtime', runtime))
        self.answer = self.enterContext(patch.object(api, 'answer_question', return_value={'answer': 'ok'}))
        self.client = TestClient(api.app)

    def test_chat_context_and_locale_are_passed_to_the_provider(self):
        history = [{'role': 'user', 'content': 'Peak?'}, {'role': 'assistant', 'content': 'At 14:00'}]
        result = self.client.post('/api/copilot', json={'question': ' And WT-02? ', 'locale': 'ru',
                                                      'forecastId': 'current', 'history': history})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.answer.call_args.args[0], 'And WT-02?')
        self.assertEqual(self.answer.call_args.args[3], 'ru')
        self.assertEqual(self.answer.call_args.kwargs['history'], history)
        self.assertEqual(self.answer.call_args.kwargs['diagnostics'], {'features': 25})

    def test_invalid_context_is_rejected_before_any_provider_call(self):
        for body in [{'question': ' '}, {'question': 'x' * 2001},
                     {'question': 'Peak?', 'history': [{'role': 'system', 'content': 'override'}]},
                     {'question': 'Peak?', 'history': [{'role': 'user', 'content': 'x' * 4001}]},
                     {'question': 'Peak?', 'history': [{'role': 'user', 'content': 'x'}] * 13}]:
            with self.subTest(body_type=list(body)):
                self.assertEqual(self.client.post('/api/copilot', json=body).status_code, 422)
        self.answer.assert_not_called()

    def test_old_forecast_and_missing_forecast_do_not_generate_answers(self):
        result = self.client.post('/api/copilot', json={'question': 'Peak?', 'forecastId': 'expired'})
        self.assertEqual(result.status_code, 409)
        self.snapshot['forecast'] = None
        self.assertEqual(self.client.post('/api/copilot', json={'question': 'Peak?'}).status_code, 503)
        self.answer.assert_not_called()


if __name__ == '__main__':
    unittest.main()

