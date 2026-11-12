import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
IMPORT_DATA = tempfile.TemporaryDirectory()
os.environ['JARVIS_DATA_DIR'] = IMPORT_DATA.name
import app as jarvis
from settings_store import SettingsManager
from runtime_utils import provider_deadline
from ai_engine import ProviderState


class JarvisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        data = Path(self.temp.name)
        jarvis.settings_manager = SettingsManager(data / 'settings.json', {**jarvis.DEFAULT_SETTINGS, 'tts_engine': 'edge'})
        jarvis.db_manager = jarvis.DatabaseManager(str(data / 'test.sqlite'))
        jarvis.AUDIO_CACHE_DIR = str(data)
        jarvis.app.config.update(TESTING=True)
        self.client = jarvis.app.test_client()
        timbre_patch = patch.object(jarvis, 'apply_voice_timbre', side_effect=lambda audio, effect: audio)
        self.timbre = timbre_patch.start()
        self.addCleanup(timbre_patch.stop)
        jarvis.LLMEngine.health = ProviderState()

    def test_pages_and_status(self):
        for page in ('/', '/settings', '/credits', '/api/status', '/api/history', '/api/providers'):
            self.assertEqual(self.client.get(page).status_code, 200, page)
        self.assertEqual(self.client.get('/api/status').json['app_version'], '2.0.0')

    def test_secrets_never_returned_to_browser(self):
        jarvis.settings_manager.update({'groq_api_key': 'secret-test-key'})
        for path in ('/', '/settings', '/api/status', '/api/providers'):
            self.assertNotIn(b'secret-test-key', self.client.get(path).data)
        result = self.client.post('/api/save_settings', json={'user_name': 'Test'})
        self.assertNotIn(b'secret-test-key', result.data)
        self.assertTrue(result.json['settings']['secrets_configured']['groq_api_key'])

    def test_blank_api_key_preserves_existing(self):
        jarvis.settings_manager.update({'groq_api_key': 'keep-me'})
        result = self.client.post('/api/save_settings', json={'groq_api_key': '', 'user_name': 'Nuovo'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(jarvis.settings_manager.get('groq_api_key'), 'keep-me')
        self.assertEqual(jarvis.settings_manager.get('user_name'), 'Nuovo')

    def test_invalid_settings_do_not_partially_save(self):
        result = self.client.post('/api/save_settings', json={'assistant_name': 'Changed', 'voice_pitch_hz': 'deep'})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(jarvis.settings_manager.get('assistant_name'), 'AURA')
        self.assertFalse(jarvis.settings_manager.filepath.exists())

    def test_settings_validation(self):
        for bad in ({'wake_enabled': 'false'}, {'voice_rate_percent': 100}, {'model': []},
                    {'groq_api_key': None}, {'ollama_host': 'http://user:pass@example.com'},
                    {'unknown': 'x'}, {'schema_version': 0}, {'user_name': '<' * 100}):
            self.assertEqual(self.client.post('/api/save_settings', json=bad).status_code, 400, bad)

    def test_invalid_chat_inputs_are_400(self):
        for bad in ([], ['hello'], {}, {'message': 123}, {'message': None}, {'message': '\x00'}, {'message': 'a' * 6001}):
            self.assertEqual(self.client.post('/api/chat', json=bad).status_code, 400, bad)

    def test_same_origin_json_required(self):
        self.assertEqual(self.client.post('/api/chat', data='message=hello').status_code, 415)
        self.assertEqual(self.client.post('/api/clear_chat', headers={'Origin': 'https://external.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/history', headers={'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
        self.assertEqual(self.client.get('/api/history', base_url='http://evil.example').status_code, 400)

    def test_ai_settings_are_validated_and_saved(self):
        response = self.client.post('/api/save_settings', json={'ai_mode': 'reasoning', 'allow_fallback': False,
                    'context_turns': 20, 'max_response_tokens': 4096})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['settings']['ai_mode'], 'reasoning')
        for data in ({'ai_mode': 'unknown'}, {'context_turns': 1000}, {'context_chars': 1},
                     {'max_response_tokens': 99999}, {'allow_fallback': 'yes'}):
            self.assertEqual(self.client.post('/api/save_settings', json=data).status_code, 400)

    def test_ai_check_does_not_save_or_change_conversation(self):
        with patch.object(jarvis.LLMEngine, 'diagnose', return_value=[{'id':'groq', 'state':'not_configured'}]):
            response = self.client.post('/api/ai/check', json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(jarvis.db_manager.get_message_count(), 0)

    def test_parallel_ai_check_returns_409(self):
        jarvis.ai_check_lock.acquire()
        try:
            self.assertEqual(self.client.post('/api/ai/check', json={}).status_code, 409)
        finally:
            jarvis.ai_check_lock.release()

    def test_openrouter_connection_uses_fixed_test_without_history(self):
        jarvis.db_manager.save_chat_message('user', 'private-history-marker')
        key = 'sk-or-v1-test-key-not-a-real-secret'
        with patch.object(jarvis.LLMEngine, 'call_openrouter', return_value='Ciao, sono Aura. Collegamento riuscito.') as call:
            response = self.client.post('/api/connect/openrouter', json={'key':key})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(key.encode(), response.data)
        self.assertNotIn('private-history-marker', str(call.call_args))
        self.assertEqual(jarvis.db_manager.get_message_count(), 1)
        self.assertEqual(jarvis.settings_manager.get('model'), 'openrouter:openrouter/free')
        self.assertFalse(jarvis.settings_manager.get('allow_fallback'))

    def test_openrouter_auth_error_is_safe_and_keeps_saved_key(self):
        key = 'sk-or-v1-test-key-not-a-real-secret'
        error = jarvis.requests.HTTPError('must-not-leak')
        error.response = jarvis.requests.Response()
        error.response.status_code = 401
        with patch.object(jarvis.LLMEngine, 'call_openrouter', side_effect=error):
            response = self.client.post('/api/connect/openrouter', json={'key':key})
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.json['key_saved'])
        self.assertEqual(jarvis.settings_manager.get('openrouter_api_key'), key)
        self.assertNotIn(b'must-not-leak', response.data)

    def test_openrouter_missing_or_invalid_key_is_not_sent(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY':''}), patch.object(jarvis.LLMEngine, 'call_openrouter') as call:
            for data in ({}, [], {'key':4}, {'key':'short'}, {'key':'a key containing spaces'}):
                self.assertEqual(self.client.post('/api/connect/openrouter', json=data).status_code, 400)
        call.assert_not_called()

    def test_dialect_preferences_are_validated(self):
        for data in ({'dialect_intensity':'unknown'}, {'pronunciation_mode':'translate'}):
            self.assertEqual(self.client.post('/api/save_settings', json=data).status_code, 400)
        self.assertEqual(self.client.post('/api/save_settings', json={'dialect_intensity':'authentic','pronunciation_mode':'assisted'}).status_code, 200)
        self.assertEqual(self.client.get('/api/dialects').status_code, 200)

    def test_aura_brand_and_secret_free_setup_are_rendered(self):
        page = self.client.get('/').get_data(as_text=True)
        self.assertIn('AURA', page)
        self.assertIn('css/aura.css', page)
        self.assertNotIn('telemetry-panel', page)
        self.assertIn('Collega AURA', page)
        self.assertEqual(jarvis.DEFAULT_SETTINGS['voice_name'], 'it-IT-ElsaNeural')
        self.assertEqual(jarvis.DEFAULT_SETTINGS['voice_pitch_hz'], 0)

    def test_json_object_with_braces_and_newlines(self):
        text = 'Esempio {a}:\n```python\nprint("ciao")\n```'
        result = jarvis.LLMEngine.parse_json_response('```json\n' + json.dumps({'testo': text, 'emozione': 'happy'}) + '\n```')
        self.assertEqual(result, (text, 'felice'))

    def test_plain_code_reply_not_destroyed(self):
        text = 'Ecco il codice:\n```python\nprint({"a": 1})\n```'
        self.assertEqual(jarvis.LLMEngine.parse_json_response(text), (text, 'normale'))

    def test_unknown_or_non_string_emotion_is_neutral(self):
        for emotion in (None, [], 'not-real'):
            self.assertEqual(jarvis.LLMEngine.parse_json_response(json.dumps({'testo': 'Ciao', 'emozione': emotion})), ('Ciao', 'normale'))

    def test_multiline_input_preserved(self):
        text = 'def hello():\n\treturn 1\n\nUna lista:\n- uno'
        self.assertEqual(jarvis.LLMEngine.sanitize_input(text), (True, text))

    def test_chat_saves_pair_and_history_without_provider_calls(self):
        with patch.object(jarvis.LLMEngine, 'generate_response', return_value=('Pronto.', 'felice', 'test', 'mock')) as call:
            response = self.client.post('/api/chat', json={'message': 'Ciao\nJarvis'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(call.call_args.args[0], 'Ciao\nJarvis')
        self.assertEqual(response.json['memory_count'], 2)
        self.assertEqual([item['role'] for item in self.client.get('/api/history').json['messages']], ['user', 'bot'])

    def test_concurrent_chat_and_clear_return_409(self):
        jarvis.chat_lock.acquire()
        try:
            self.assertEqual(self.client.post('/api/chat', json={'message': 'Ciao'}).status_code, 409)
            self.assertEqual(self.client.post('/api/clear_chat').status_code, 409)
        finally:
            jarvis.chat_lock.release()

    def test_offline_reply_is_not_saved_and_lock_is_released(self):
        with patch.object(jarvis.LLMEngine, 'generate_response', return_value=('Servizio non disponibile', 'allerta', 'offline', 'none')):
            response = self.client.post('/api/chat', json={'message': 'Ciao'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(jarvis.db_manager.get_message_count(), 0)
        self.assertFalse(jarvis.chat_lock.locked())

    def test_unexpected_provider_error_releases_lock(self):
        with patch.object(jarvis.LLMEngine, 'generate_response', side_effect=RuntimeError('private-info')):
            response = self.client.post('/api/chat', json={'message': 'Ciao'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private-info', response.data)
        self.assertFalse(jarvis.chat_lock.locked())

    def test_history_count_is_total_and_legacy_words_do_not_hide_messages(self):
        for number in range(105):
            jarvis.db_manager.save_chat_message('bot', f'Nota {number}: cosa significa kawaii?')
        response = self.client.get('/api/history?limit=2')
        self.assertEqual(response.json['count'], 105)
        self.assertEqual(len(response.json['messages']), 2)
        self.assertEqual(self.client.get('/api/status').json['memory_count'], 105)

    def test_auth_failure_has_useful_safe_message(self):
        failure = jarvis.requests.HTTPError('secret')
        failure.response = jarvis.requests.Response()
        failure.response.status_code = 401
        with patch.object(jarvis.LLMEngine, 'provider_candidates', return_value=[('groq', 'one')]), \
             patch.object(jarvis.LLMEngine, 'call_provider', side_effect=failure):
            result = jarvis.LLMEngine.generate_response('Ciao', [], {**jarvis.DEFAULT_SETTINGS, 'model':'auto:free', 'groq_api_key': 'test'})
        self.assertIn('401', result[0])
        self.assertNotIn('secret', result[0])
        self.assertEqual(result[2], 'offline')

    def test_provider_fallback_and_deadline_cleanup(self):
        with patch.object(jarvis.LLMEngine, 'provider_candidates', return_value=[('groq', 'one'), ('groq', 'two')]), \
             patch.object(jarvis.LLMEngine, 'call_provider', side_effect=[RuntimeError('failed'), '{"testo":"OK","emozione":"normale"}']):
            result = jarvis.LLMEngine.generate_response('Ciao', [], {**jarvis.DEFAULT_SETTINGS, 'model':'auto:free'})
        self.assertEqual(result, ('OK', 'normale', 'groq', 'two'))
        self.assertIsNone(provider_deadline.get())

    def test_gemini_key_in_header_and_system_instruction(self):
        with patch.object(jarvis.requests, 'post') as post:
            post.return_value.json.return_value = {'candidates': [{'content': {'parts': [{'text': 'OK'}]}}]}
            jarvis.LLMEngine.call_gemini('private-key', 'model', [{'role': 'system', 'content': 'System'}, {'role': 'user', 'content': 'Hi'}])
        self.assertNotIn('private-key', post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs['headers']['x-goog-api-key'], 'private-key')
        self.assertIn('systemInstruction', post.call_args.kwargs['json'])

    def test_tts_post_cache(self):
        with patch.object(jarvis.TTSEngine, 'generate_speech', return_value=b'ID3-test-audio') as speech:
            first = self.client.post('/api/tts', json={'text': 'Ciao'})
            second = self.client.post('/api/tts', json={'text': 'Ciao'})
            self.assertEqual(first.data, second.data)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(speech.call_count, 1)
            first.close()
            second.close()
        self.assertEqual(self.client.get('/api/tts?text=private').status_code, 405)

    def test_cozy_preferences_validate_atomically(self):
        for key in ('personality_profile', 'nerd_intensity', 'voice_character'):
            before = jarvis.settings_manager.get_all()
            response = self.client.post('/api/save_settings', json={key: 'invalid', 'assistant_name': 'Changed'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(jarvis.settings_manager.get_all(), before)
        result = self.client.post('/api/save_settings', json={
            'personality_profile': 'neutral', 'nerd_intensity': 'gentle', 'voice_character': 'natural'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(jarvis.settings_manager.get('personality_profile'), 'neutral')

    def test_changing_voice_character_invalidates_audio_cache(self):
        with patch.object(jarvis.TTSEngine, 'generate_speech', return_value=b'ID3-test-audio') as speech:
            with self.client.post('/api/tts', json={'text': 'Profilo voce'}) as first:
                self.assertEqual(first.status_code, 200)
            jarvis.settings_manager.update({'voice_character': 'natural'})
            with self.client.post('/api/tts', json={'text': 'Profilo voce'}) as second:
                self.assertEqual(second.status_code, 200)
            self.assertEqual(speech.call_count, 2)
            self.assertEqual(speech.call_args.args[-1], 'natural')

    def test_voice_timbre_is_validated_and_invalidates_audio_cache(self):
        self.assertEqual(self.client.post('/api/save_settings', json={'voice_effect': 'unknown'}).status_code, 400)
        with patch.object(jarvis.TTSEngine, 'generate_speech', return_value=b'ID3-test-audio'):
            for mode in ('none', 'young', 'anime'):
                jarvis.settings_manager.update({'voice_effect': mode})
                with self.client.post('/api/tts', json={'text':'Timbro distinto'}) as result:
                    self.assertEqual(result.status_code, 200)
                self.assertEqual(self.timbre.call_args.args[-1], mode)
            self.assertEqual(self.timbre.call_count, 3)

    def test_voice_timbre_failure_does_not_cache_unprocessed_audio(self):
        self.timbre.side_effect = RuntimeError('private-audio-details')
        with patch.object(jarvis.TTSEngine, 'generate_speech', return_value=b'ID3-unprocessed'):
            response = self.client.post('/api/tts', json={'text':'Errore di elaborazione'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private-audio-details', response.data)
        self.assertFalse(list(Path(jarvis.AUDIO_CACHE_DIR).glob('*.mp3')))

    def test_local_voice_is_wav_cached_and_never_pitch_processed(self):
        jarvis.settings_manager.update({'tts_engine':'kokoro', 'local_voice_style':'hiyori', 'voice_effect':'anime'})
        with patch.object(jarvis, 'generate_local_speech', return_value=b'RIFF-test-audio') as synth:
            with self.client.post('/api/tts', json={'text':'Voce locale'}) as first:
                self.assertEqual(first.mimetype, 'audio/wav')
                self.assertEqual(first.data, b'RIFF-test-audio')
            with self.client.post('/api/tts', json={'text':'Voce locale'}) as second:
                self.assertEqual(second.data, b'RIFF-test-audio')
            self.assertEqual(synth.call_count, 1)
        self.timbre.assert_not_called()
        self.assertEqual(len(list(Path(jarvis.AUDIO_CACHE_DIR).glob('*.wav'))), 1)

    def test_local_voice_switches_style_and_preserves_errors(self):
        with patch.object(jarvis, 'generate_local_speech', return_value=b'RIFF-test-audio') as synth:
            for style in ('hiyori', 'hiyori_soft'):
                jarvis.settings_manager.update({'tts_engine':'kokoro','local_voice_style':style})
                with self.client.post('/api/tts', json={'text':'Stile diverso'}) as response:
                    self.assertEqual(response.status_code, 200)
                self.assertEqual(synth.call_args.args[1], style)
            self.assertEqual(synth.call_count, 2)
        for bad in ({'tts_engine':'unknown'}, {'local_voice_style':'../../.env'}):
            self.assertEqual(self.client.post('/api/save_settings', json=bad).status_code, 400)

    def test_local_voice_failure_does_not_send_text_to_edge(self):
        jarvis.settings_manager.update({'tts_engine':'kokoro'})
        with patch.object(jarvis, 'generate_local_speech', side_effect=RuntimeError('private-details')), \
             patch.object(jarvis.TTSEngine, 'generate_speech') as online:
            response = self.client.post('/api/tts', json={'text':'Testo riservato'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private-details', response.data)
        online.assert_not_called()

    def test_new_neural_voices_are_separate_and_skip_pitch_effects(self):
        for engine, function in [('qwen','generate_qwen_speech'),('irodori','generate_irodori_speech')]:
            jarvis.settings_manager.update({'tts_engine':engine,'voice_effect':'anime','hf_api_key':'hf_unit_test_only'})
            with patch.object(jarvis,function,return_value=b'voice') as synthesize, \
                 patch.object(jarvis.TTSEngine,'generate_speech') as edge:
                with self.client.post('/api/tts',json={'text':'Una voce '+engine}) as result:
                    self.assertEqual(result.status_code,200)
                    self.assertEqual(result.mimetype,'audio/wav')
            synthesize.assert_called_once()
            edge.assert_not_called()
        self.timbre.assert_not_called()

    def test_neural_setup_errors_are_visible_without_online_fallback(self):
        jarvis.settings_manager.update({'tts_engine':'qwen'})
        with patch.object(jarvis,'generate_qwen_speech',side_effect=jarvis.NeuralVoiceError('Qwen non è pronto.')), \
             patch.object(jarvis.TTSEngine,'generate_speech') as edge:
            result=self.client.post('/api/tts',json={'text':'Frase privata'})
        self.assertEqual(result.status_code,503)
        self.assertEqual(result.json['error'],'Qwen non è pronto.')
        edge.assert_not_called()

    def test_huggingface_voice_token_stays_private_and_new_styles_are_validated(self):
        jarvis.settings_manager.update({'hf_api_key':'hf_private_voice_test_only'})
        for path in ('/','/settings','/api/status'):
            self.assertNotIn(b'hf_private_voice_test_only',self.client.get(path).data)
        for data in ({'qwen_voice_style':'../../secret'},{'irodori_reading':'translate'}):
            self.assertEqual(self.client.post('/api/save_settings',json=data).status_code,400)

    def test_edge_receives_cozy_prosody_and_original_dialect(self):
        class FakeCommunicator:
            async def stream(self):
                yield {'type': 'audio', 'data': b'ID3-cozy'}
        with patch.object(jarvis.edge_tts, 'Communicate', return_value=FakeCommunicator()) as communicate:
            result = jarvis.TTSEngine.generate_speech('Jamme, ’na cosa â vota.', 'felice', False,
                'none', 'napoletano', 'it-IT-IsabellaNeural', 3, 2, 'cozy')
        self.assertEqual(result, b'ID3-cozy')
        self.assertEqual(communicate.call_args.args, ('Jamme, ’na cosa â vota.', 'it-IT-IsabellaNeural'))
        self.assertEqual(communicate.call_args.kwargs['pitch'], '+5Hz')
        self.assertEqual(communicate.call_args.kwargs['rate'], '+5%')
        self.assertEqual(communicate.call_args.kwargs['volume'], '-3%')

    def test_tts_rejects_invalid_data_and_hides_errors(self):
        for data in ([], {'text': 4}, {'text': 'a' * 2501}, {'text': 'Ciao', 'emotion': []}):
            self.assertEqual(self.client.post('/api/tts', json=data).status_code, 400)
        with patch.object(jarvis.TTSEngine, 'generate_speech', side_effect=RuntimeError('secret-key')):
            response = self.client.post('/api/tts', json={'text': 'test'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'secret-key', response.data)

    @unittest.skipUnless((ROOT/'static/models/haru/Haru.model3.json').exists(), 'Prepara gli asset Live2D opzionali per verificarli')
    def test_assets_are_local_and_match_checksums(self):
        manifest = json.loads((ROOT / 'asset-manifest.json').read_text())
        self.assertGreater(len(manifest), 20)
        for entry in manifest:
            path = ROOT / entry['path']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'], entry['path'])
        model = json.loads((ROOT / 'static/models/haru/Haru.model3.json').read_text())
        self.assertFalse(any('Sound' in motion for motions in model['FileReferences']['Motions'].values() for motion in motions))
        page = self.client.get('/').get_data(as_text=True)
        self.assertNotIn('nexus_avatar.svg', page)
        self.assertIn('js/avatar.js', page)

    def test_avatar_choice_updates_character_credit_and_runtime_together(self):
        for selected, name in (('hiyori', 'Hiyori'), ('haru', 'Haru')):
            result = self.client.post('/api/save_settings', json={'avatar_model': selected})
            self.assertEqual(result.status_code, 200)
            page = self.client.get('/').get_data(as_text=True)
            self.assertIn(name + ' © Live2D Inc.', page)
            self.assertIn(f'/static/models/{selected}/{name}.model3.json', page)
            self.assertIn(name + ' © Live2D Inc.', self.client.get('/credits').get_data(as_text=True))

    def test_avatar_does_not_accept_arbitrary_paths_or_remote_models(self):
        for invalid in ('../../.env', 'https://example.com/model.json', 'unknown'):
            response = self.client.post('/api/save_settings', json={'avatar_model': invalid})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(jarvis.settings_manager.get('avatar_model'), 'hiyori')

    @unittest.skipUnless((ROOT/'static/models/hiyori/Hiyori.model3.json').exists(), 'Prepara gli asset Live2D opzionali per verificarli')
    def test_hiyori_references_local_assets_and_expressions_preserve_lips(self):
        directory = ROOT / 'static/models/hiyori'
        model = json.loads((directory / 'Hiyori.model3.json').read_text())
        refs = model['FileReferences']
        files = [refs[key] for key in ('Moc', 'Physics', 'Pose', 'DisplayInfo') if key in refs]
        files += refs['Textures'] + [value['File'] for value in refs['Expressions']]
        for group in refs['Motions'].values():
            for motion in group:
                self.assertNotIn('Sound', motion)
                files.append(motion['File'])
        for name in files:
            self.assertTrue((directory / name).resolve().is_relative_to(directory.resolve()))
            self.assertTrue((directory / name).is_file(), name)
        supported = {entry['Id'] for entry in json.loads((directory / refs['DisplayInfo']).read_text(encoding='utf-8'))['Parameters']}
        for entry in refs['Expressions']:
            expression = json.loads((directory / entry['File']).read_text())
            self.assertTrue(all(param['Id'] in supported for param in expression['Parameters']))
            self.assertNotIn('ParamMouthOpenY', [param['Id'] for param in expression['Parameters']])


if __name__ == '__main__':
    unittest.main()
