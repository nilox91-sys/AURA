"""Conversation privacy and secret-free templates use the running application routes."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import test_app as base
jarvis=base.jarvis

class PreferencesTests(unittest.TestCase):
    setUp=base.JarvisTests.setUp

    def test_disabled_history_does_not_read_or_save_turns(self):
        jarvis.db_manager.save_chat_message('user','already saved')
        jarvis.settings_manager.update({'history_enabled':False})
        with patch.object(jarvis.LLMEngine,'generate_response',return_value=('ciao','normale','mock','one')) as generate:
            response=self.client.post('/api/chat',json={'message':'new private turn'})
        self.assertEqual(response.status_code,200);self.assertEqual(generate.call_args.args[1],[])
        self.assertEqual(jarvis.db_manager.get_message_count(),1)
        self.assertEqual(self.client.get('/api/history').json['messages'],[])

    def test_extended_keys_stay_private_and_identity_is_escaped(self):
        jarvis.settings_manager.update({'openai_api_key':'never-public','anthropic_api_key':'also-private',
                                        'assistant_tagline':'<script>bad()</script>'})
        for path in ('/','/settings','/api/status','/api/providers'):
            response=self.client.get(path)
            self.assertNotIn(b'never-public',response.data);self.assertNotIn(b'also-private',response.data)
        self.assertIn(b'&lt;script&gt;',self.client.get('/').data)
        self.assertEqual(len(self.client.get('/api/providers').json['providers']),11)

    def test_github_lock_cannot_be_enabled_before_authentication(self):
        response=self.client.post('/api/save_settings',json={'github_require_login':True,'assistant_name':'Changed'})
        self.assertEqual(response.status_code,400)
        self.assertFalse(jarvis.settings_manager.get('github_require_login'))
        self.assertEqual(jarvis.settings_manager.get('assistant_name'),'AURA')

    def test_disabled_audio_cache_does_not_read_or_write(self):
        jarvis.settings_manager.update({'tts_cache_enabled':False})
        with patch.object(jarvis.TTSEngine,'generate_speech',return_value=b'ID3') as speech:
            for _ in range(2):
                self.assertEqual(self.client.post('/api/tts',json={'text':'ciao'}).status_code,200)
        self.assertEqual(speech.call_count,2)
        self.assertFalse(list(Path(jarvis.AUDIO_CACHE_DIR).glob('*.mp3')))
