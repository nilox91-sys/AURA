import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_engine import LLMEngine, ProviderState, IncompleteResponseError, generation_info
from runtime_utils import provider_deadline


class AIEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = LLMEngine
        self.engine.health = ProviderState()
        self.settings = {'model': 'auto:free', 'groq_api_key': 'test-key', 'ai_mode': 'balanced',
                         'allow_fallback': True, 'max_response_tokens': 2048, 'context_chars': 16000, 'context_turns': 12}
        self.environment = patch.dict('os.environ', {'GEMINI_API_KEY': '', 'HF_API_KEY': '', 'OPENROUTER_API_KEY': '', 'GROQ_API_KEY': ''})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @staticmethod
    def failure(status, retry_after=None):
        response = requests.Response()
        response.status_code = status
        if retry_after:
            response.headers['Retry-After'] = retry_after
        return requests.HTTPError('sensitive-error-body', response=response)

    def test_routing_profiles(self):
        expected = {'fast': 'openai/gpt-oss-20b', 'balanced': 'qwen/qwen3.8-27b', 'reasoning': 'openai/gpt-oss-120b'}
        for mode, model in expected.items():
            settings = {**self.settings, 'ai_mode': mode}
            self.assertEqual(self.engine.provider_candidates('auto:free', settings)[0], ('groq', model))

    def test_explicit_model_is_first(self):
        self.assertEqual(self.engine.provider_candidates('groq:my-model', self.settings)[0], ('groq', 'my-model'))

    def test_local_mode_never_falls_back_to_cloud(self):
        candidates = self.engine.provider_candidates('ollama:local-model', self.settings)
        self.assertEqual(candidates, [('ollama', 'local-model')])

    def test_fallback_can_be_disabled(self):
        settings = {**self.settings, 'allow_fallback': False}
        self.assertEqual(len(self.engine.provider_candidates('auto:free', settings)), 1)
        self.assertEqual(self.engine.provider_candidates('groq:custom', settings), [('groq', 'custom')])

    def test_context_preserves_complete_recent_turns(self):
        history = [{'role': 'bot', 'content': 'orphan'}]
        for index in range(4):
            history.extend([{'role': 'user', 'content': f'U{index}'}, {'role': 'bot', 'content': f'A{index}'}])
        messages, info = self.engine.build_messages('Current', history, {**self.settings, 'context_turns': 2})
        self.assertEqual([message['content'] for message in messages[1:]], ['U2', 'A2', 'U3', 'A3', 'Current'])
        self.assertEqual(info['turns_used'], 2)
        self.assertEqual(info['turns_omitted'], 2)

    def test_context_character_budget_does_not_cut_code(self):
        history = [{'role': 'user', 'content': 'x' * 100}, {'role': 'bot', 'content': 'y' * 100},
                   {'role': 'user', 'content': 'new'}, {'role': 'bot', 'content': '```python\nprint(1)\n```'}]
        messages, info = self.engine.build_messages('now', history, {**self.settings, 'context_chars': 50})
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[2]['content'], history[-1]['content'])
        self.assertLessEqual(info['history_characters'], 50)

    def test_oversized_latest_turn_does_not_restore_unrelated_old_turn(self):
        history = [{'role': 'user', 'content': 'old'}, {'role': 'bot', 'content': 'old'},
                   {'role': 'user', 'content': 'x' * 100}, {'role': 'bot', 'content': 'y' * 100}]
        messages, info = self.engine.build_messages('now', history, {**self.settings, 'context_chars': 50})
        self.assertEqual(len(messages), 2)
        self.assertEqual(info['turns_used'], 0)

    def test_json_example_in_plain_code_answer_is_not_confused_with_envelope(self):
        text = 'Esempio di JSON:\n```json\n{"testo":"esempio","emozione":"felice"}\n```'
        self.assertEqual(self.engine.parse_json_response(text), (text, 'normale'))

    def test_auth_error_skips_other_models_of_same_provider(self):
        with patch.object(self.engine, 'provider_candidates', return_value=[('groq', 'one'), ('groq', 'two')]), \
             patch.object(self.engine, 'call_provider', side_effect=self.failure(401)) as call:
            result = self.engine.generate_response('Hi', [], self.settings)
            second = self.engine.generate_response('Again', [], self.settings)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result[2], 'offline')
        self.assertIn('Verifica di aver usato una chiave API', second[0])
        self.assertNotIn('sensitive-error-body', result[0])

    def test_new_key_bypasses_old_auth_cooldown(self):
        keys = self.engine.provider_keys(self.settings)
        self.engine.health.failure('groq', keys, 'model', self.failure(401))
        changed = {**self.settings, 'groq_api_key': 'new-test-key'}
        with patch.object(self.engine, 'provider_candidates', return_value=[('groq', 'model')]), \
             patch.object(self.engine, 'call_provider', return_value='{"testo":"OK","emozione":"felice"}') as call:
            result = self.engine.generate_response('Hi', [], changed)
        self.assertEqual(result[0], 'OK')
        self.assertEqual(call.call_count, 1)

    def test_rate_limit_is_per_model_and_honors_retry_after(self):
        keys = self.engine.provider_keys(self.settings)
        self.engine.health.failure('groq', keys, 'one', self.failure(429, '55'))
        self.assertGreaterEqual(self.engine.health.blocked('groq', keys, 'one')['retry_after'], 54)
        self.assertIsNone(self.engine.health.blocked('groq', keys, 'two'))

    def test_retry_after_is_bounded(self):
        keys = self.engine.provider_keys(self.settings)
        self.engine.health.failure('groq', keys, 'one', self.failure(429, '99999'))
        self.assertLessEqual(self.engine.health.blocked('groq', keys, 'one')['retry_after'], 121)

    def test_success_does_not_forget_other_missing_model(self):
        keys = self.engine.provider_keys(self.settings)
        self.engine.health.failure('groq', keys, 'missing', self.failure(404))
        self.engine.health.success('groq', keys, model='working')
        self.assertIsNotNone(self.engine.health.blocked('groq', keys, 'missing'))

    def test_healthy_model_catalog_filters_retired_defaults(self):
        keys = self.engine.provider_keys(self.settings)
        self.engine.health.success('groq', keys, models=['openai/gpt-oss-120b'], verified=True)
        candidates = self.engine.provider_candidates('auto:free', self.settings)
        self.assertEqual(candidates[0], ('groq', 'openai/gpt-oss-120b'))

    def test_truncated_json_retries_once_with_larger_budget(self):
        budgets = []
        def call(*args):
            budgets.append(self.engine.options()['max_tokens'])
            return '{"emozione":"normale","testo":"unfinished' if len(budgets) == 1 else '{"testo":"Complete","emozione":"normale"}'
        with patch.object(self.engine, 'provider_candidates', return_value=[('groq', 'one')]), \
             patch.object(self.engine, 'call_provider', side_effect=call):
            result = self.engine.generate_response('Hi', [], self.settings)
        self.assertEqual(budgets, [2048, 4096])
        self.assertEqual(result[0], 'Complete')
        self.assertIsNone(provider_deadline.get())

    def test_unbounded_repair_is_prevented(self):
        with patch.object(self.engine, 'provider_candidates', return_value=[('groq', 'one')]), \
             patch.object(self.engine, 'call_provider', side_effect=IncompleteResponseError('incomplete')) as call:
            result = self.engine.generate_response('Hi', [], {**self.settings, 'max_response_tokens': 8192})
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result[2], 'offline')

    def test_groq_schema_and_reasoning_budget(self):
        response = Mock()
        response.json.return_value = {'choices': [{'message': {'content': '{"testo":"OK","emozione":"normale"}'}, 'finish_reason': 'stop'}],
                                      'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13}}
        with patch('ai_engine.requests.post', return_value=response) as post:
            self.engine.generate_response('Hi', [], {**self.settings, 'ai_mode': 'reasoning', 'allow_fallback': False})
        payload = post.call_args.kwargs['json']
        self.assertTrue(payload['response_format']['json_schema']['strict'])
        self.assertEqual(payload['reasoning_effort'], 'medium')
        self.assertEqual(generation_info.get()['usage']['total_tokens'], 13)

    def test_ollama_uses_native_schema_and_no_stream(self):
        response = Mock()
        response.json.return_value = {'message': {'content': '{"testo":"OK"}'}, 'done_reason': 'stop'}
        with patch('ai_engine.requests.post', return_value=response) as post:
            self.engine.call_ollama('http://localhost:11434', 'local', [{'role': 'user', 'content': 'Hi'}])
        self.assertTrue(post.call_args.args[0].endswith('/api/chat'))
        self.assertFalse(post.call_args.kwargs['json']['stream'])
        self.assertEqual(post.call_args.kwargs['json']['format']['type'], 'object')

    def test_diagnostics_do_not_generate_or_send_history(self):
        response = Mock()
        response.json.return_value = {'data': [{'id': 'openai/gpt-oss-20b'}]}
        with patch('ai_engine.requests.get', return_value=response) as get, patch('ai_engine.requests.post') as post:
            results = self.engine.diagnose(self.settings)
        post.assert_not_called()
        self.assertEqual(next(item for item in results if item['id'] == 'groq')['state'], 'available')
        for call in get.call_args_list:
            self.assertNotIn('json', call.kwargs)
            self.assertNotIn('data', call.kwargs)
        self.assertNotIn('test-key', json.dumps(results))


if __name__ == '__main__':
    unittest.main()
