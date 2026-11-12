import json
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))
import test_app as base
from ai_engine import LLMEngine, PartialResponseError, REPLY_SCHEMA
from provider_registry import PROVIDERS
from provider_stream import stream_provider, stream_request, StreamIncompleteError
from provider_errors import ProviderHTTPError
from reply_stream import ReplyDecoder
from runtime_utils import provider_deadline

jarvis = base.jarvis


class DecoderTests(unittest.TestCase):
    def test_every_byte_boundary_decodes_escaped_dialect_and_unicode_without_envelope(self):
        text = 'Jamme! "Chesta" è na prova. 🎮\nSeconda frase.'
        raw = '```json\n' + json.dumps({'emozione': 'felice', 'testo': text}) + '\n```'
        decoder = ReplyDecoder()
        chunks = [decoder.feed(char) for char in raw]
        self.assertEqual(''.join(chunks), text)
        self.assertEqual(decoder.emotion, 'felice')
        self.assertTrue(any(chunks[:raw.index('Seconda')]))

    def test_text_first_envelope_and_plain_markdown(self):
        for raw, expected in [('{"testo":"Ciao.","emozione":"felice"}', 'Ciao.'),
                              ('Esempio:\n```py\na=1\n```', 'Esempio:\n```py\na=1\n```')]:
            decoder = ReplyDecoder()
            self.assertEqual(''.join(decoder.feed(c) for c in raw), expected)


class TransportTests(unittest.TestCase):
    def run_stream(self, provider, events, *, sse=True, info=None):
        response = Mock(status_code=200)
        response.headers = {}
        lines = []
        for event in events:
            if sse:
                lines.extend([': keepalive', 'data: ' + json.dumps(event), ''])
            else:
                lines.append(json.dumps(event))
        response.iter_lines.return_value = iter(lines)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.post.return_value = response
        with patch('provider_stream.requests.Session', return_value=session):
            return list(stream_provider(provider, 'test-model', [], {'ollama_host': 'http://localhost:11434'},
                                        {'max_tokens': 128}, REPLY_SCHEMA, info if info is not None else {}))

    def test_gemini_excludes_thoughts_and_requires_finish(self):
        chunks = self.run_stream('gemini', [
            {'candidates': [{'content': {'parts': [{'text': 'secret reasoning', 'thought': True}, {'text': 'Prima. '}]}}]},
            {'candidates': [{'content': {'parts': [{'text': 'Seconda.'}]}, 'finishReason': 'STOP'}]},
        ])
        self.assertEqual(chunks, ['Prima. ', 'Seconda.'])
        with self.assertRaises(StreamIncompleteError):
            self.run_stream('gemini', [{'candidates': [{'content': {'parts': [{'text': 'Parziale.'}]}}]}])

    def test_native_streams_only_emit_final_answer_text(self):
        cases = [
            ('openai', [{'type': 'response.reasoning_summary_text.delta', 'delta': 'private'},
                        {'type': 'response.output_text.delta', 'delta': 'Ciao.'}, {'type': 'response.completed'}]),
            ('anthropic', [{'type': 'content_block_delta', 'delta': {'type': 'thinking_delta', 'thinking': 'private'}},
                           {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'Ciao.'}}, {'type': 'message_stop'}]),
            ('openrouter', [{'choices': [{'delta': {'reasoning': 'private', 'content': 'Ciao.'}}]},
                            {'choices': [{'delta': {}, 'finish_reason': 'stop'}]}]),
        ]
        for provider, events in cases:
            with self.subTest(provider=provider):
                self.assertEqual(self.run_stream(provider, events), ['Ciao.'])
        self.assertEqual(self.run_stream('ollama', [{'message': {'content': 'Ciao.'}}, {'done': True}], sse=False), ['Ciao.'])

    def test_all_registered_connections_have_streaming_requests_and_responses_do_not_store(self):
        from ai_engine import REPLY_SCHEMA
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                url, headers, payload, protocol = stream_request(provider, 'test', [],
                    {'ollama_host': 'http://localhost:11434', 'lmstudio_host': 'http://localhost:1234/v1',
                     'compatible_base_url': 'http://localhost:1234/v1'}, {'max_tokens': 128}, REPLY_SCHEMA)
                self.assertTrue(url.startswith(('https://', 'http://localhost')))
                if provider != 'gemini':
                    self.assertTrue(payload['stream'])
                if provider in {'openai', 'xai'}:
                    self.assertFalse(payload['store'])

    def test_midstream_error_and_length_are_not_success(self):
        for end in ({'error': {'message': 'private vendor details'}},
                    {'choices': [{'delta': {}, 'finish_reason': 'length'}]}):
            with self.assertRaises((ValueError, ProviderHTTPError)):
                self.run_stream('groq', [{'choices': [{'delta': {'content': 'Ciao.'}}]}, end])


class ConversationStreamTests(unittest.TestCase):
    setUp = base.JarvisTests.setUp

    def settings(self):
        return {**jarvis.DEFAULT_SETTINGS, 'model': 'gemini:test', 'gemini_api_key': 'test-key', 'allow_fallback': False}

    def test_first_text_arrives_before_provider_finishes_and_context_is_released(self):
        completed = []
        def source(*args):
            yield '{"emozione":"felice","testo":"Prima frase. '
            completed.append(True)
            yield 'Seconda frase."}'
        with patch('ai_engine.stream_provider', side_effect=source):
            stream = LLMEngine.stream_response('Ciao', [], self.settings())
            first = next(stream)
            self.assertEqual(first['text'], 'Prima frase. ')
            self.assertFalse(completed)
            rest = list(stream)
        self.assertEqual(rest[-1]['event'], 'done')
        self.assertIn('first_text_ms', rest[-1]['ai'])
        self.assertIsNone(provider_deadline.get())

    def test_failure_after_visible_text_never_retries_or_switches_models(self):
        def source(*args):
            yield '{"testo":"Prima frase. '
            raise RuntimeError('secret-test-key')
        with patch('ai_engine.stream_provider', side_effect=source) as call:
            stream = LLMEngine.stream_response('Ciao', [], {**self.settings(), 'allow_fallback': True})
            self.assertEqual(next(stream)['event'], 'delta')
            with self.assertRaisesRegex(PartialResponseError, 'parziale'):
                next(stream)
        self.assertEqual(call.call_count, 1)
        self.assertIsNone(provider_deadline.get())

    def test_fallback_before_first_text_keeps_one_answer(self):
        def source(provider, *args):
            if provider == 'groq':
                raise RuntimeError('upstream unavailable')
            yield '{"emozione":"felice","testo":"Jamme."}'
        with patch.object(LLMEngine, 'provider_candidates', return_value=[('groq', 'first'), ('gemini', 'second')]), \
             patch('ai_engine.stream_provider', side_effect=source):
            events = list(LLMEngine.stream_response('Ciao', [], self.settings()))
        self.assertEqual([e['event'] for e in events], ['delta', 'done'])
        self.assertEqual(events[-1]['provider'], 'gemini')
        self.assertEqual(events[-1]['ai']['attempts'], 2)

    def test_streaming_voice_preferences_are_request_only(self):
        def source(message, history, settings):
            self.assertTrue(settings['voice_mode'])
            yield {'event': 'error', 'error': 'Test'}
        with patch.object(LLMEngine, 'stream_response', side_effect=source):
            self.client.post('/api/chat', json={'message': 'Ciao', 'mode': 'voice', 'stream': True}).get_data()
        self.assertNotIn('voice_mode', jarvis.settings_manager.get_all())

    def test_stream_route_persists_only_complete_exchange_and_locks_during_generation(self):
        def source(*args):
            yield {'event': 'delta', 'text': 'Prima. '}
            yield {'event': 'done', 'status': 'success', 'response': 'Prima. Seconda.', 'emozione': 'felice', 'provider': 'test', 'model': 'test'}
        with patch.object(LLMEngine, 'stream_response', side_effect=source):
            response = self.client.post('/api/chat', json={'message': 'Ciao', 'stream': True}, buffered=False)
            iterator = iter(response.response)
            self.assertEqual(json.loads(next(iterator))['event'], 'start')
            self.assertEqual(json.loads(next(iterator))['event'], 'delta')
            self.assertEqual(jarvis.db_manager.get_message_count(), 0)
            self.assertEqual(self.client.post('/api/chat', json={'message': 'Altro'}).status_code, 409)
            events = [json.loads(line) for line in iterator]
            self.assertEqual(events[-1]['event'], 'done')
            self.assertEqual(events[-1]['memory_count'], 2)
            response.close()
        self.assertFalse(jarvis.chat_lock.locked())

    def test_disconnect_releases_lock_and_does_not_save_partial_turn(self):
        def source(*args):
            yield {'event': 'delta', 'text': 'Parziale. '}
            self.fail('A disconnected conversation must not continue consuming the provider')
        with patch.object(LLMEngine, 'stream_response', side_effect=source):
            response = self.client.post('/api/chat', json={'message': 'Ciao', 'stream': True}, buffered=False)
            iterator = iter(response.response)
            next(iterator)
            next(iterator)
            response.close()
        self.assertFalse(jarvis.chat_lock.locked())
        self.assertEqual(jarvis.db_manager.get_message_count(), 0)

    def test_failure_is_explicit_and_not_saved_or_exposed_as_raw_vendor_error(self):
        def source(*args):
            yield {'event': 'delta', 'text': 'Parziale.'}
            raise RuntimeError('private vendor details and test-key')
        with patch.object(LLMEngine, 'stream_response', side_effect=source):
            response = self.client.post('/api/chat', json={'message': 'Ciao', 'stream': True})
            events = [json.loads(line) for line in response.data.splitlines()]
        self.assertEqual(events[-1]['event'], 'error')
        self.assertNotIn('test-key', response.data.decode())
        self.assertEqual(jarvis.db_manager.get_message_count(), 0)
        self.assertFalse(jarvis.chat_lock.locked())
