import base64
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import test_app as base
jarvis=base.jarvis
from ai_engine import LLMEngine
from test_neural_voice import wav

class RealtimeTests(unittest.TestCase):
    setUp=base.JarvisTests.setUp
    def test_voice_room_has_avatar_and_no_chat(self):
        page=self.client.get('/voice')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'live2d-canvas',page.data)
        for hidden in (b'chat-messages',b'user-input',b'<textarea',b'/api/history'):
            self.assertNotIn(hidden,page.data)

    def test_voice_mode_uses_current_dialect_after_italian_history(self):
        history=[{'role':'user','content':'Ciao'},{'role':'bot','content':'Buongiorno, come posso aiutarti?'}]
        messages,_=LLMEngine.build_messages('Spiegami una cache',history,{
            **jarvis.DEFAULT_SETTINGS,'dialect':'napoletano','dialect_intensity':'authentic','voice_mode':True})
        self.assertEqual(messages[-2]['role'],'system')
        self.assertIn('non solo al saluto',messages[-2]['content'])
        self.assertIn('prevalentemente napoletano',messages[-2]['content'])
        self.assertIn('1-3 frasi',messages[0]['content'])
        self.assertNotIn('Parla in italiano naturale',messages[0]['content'])

    def test_stream_rejects_wrong_engine_and_oversized_input(self):
        self.assertEqual(self.client.post('/api/tts/stream',json={'text':'Ciao'}).status_code,409)
        for text in ('','x'*601,1):
            self.assertEqual(self.client.post('/api/tts/stream',json={'text':text}).status_code,400)

    def test_stream_delivers_ordered_audio_and_explicit_end(self):
        jarvis.settings_manager.update({'tts_engine':'qwen'})
        with patch.object(jarvis,'stream_qwen_speech',return_value=iter([wav(),wav()])):
            response=self.client.post('/api/tts/stream',json={'text':'Jamme.'})
            events=[json.loads(line) for line in response.data.splitlines()]
        self.assertEqual([x['event'] for x in events],['audio','audio','done'])
        self.assertEqual(base64.b64decode(events[0]['audio']),wav())

    def test_stream_failure_is_an_event_and_not_a_silent_end(self):
        jarvis.settings_manager.update({'tts_engine':'qwen'})
        with patch.object(jarvis,'stream_qwen_speech',side_effect=jarvis.NeuralVoiceError('Riprova')):
            response=self.client.post('/api/tts/stream',json={'text':'Jamme.'})
            event=json.loads(response.data)
        self.assertEqual(event['event'],'error')

    def test_voice_preferences_are_per_request(self):
        with patch.object(LLMEngine,'generate_response',return_value=('Jamme.','felice','test','test')) as model:
            self.client.post('/api/chat',json={'message':'Ciao','mode':'voice'})
        self.assertTrue(model.call_args.args[2]['voice_mode'])
        self.assertNotIn('voice_mode',jarvis.settings_manager.get_all())
