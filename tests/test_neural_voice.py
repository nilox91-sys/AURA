import base64
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import neural_voice as voice
from anime_reading import anime_reading


def wav():
    output=io.BytesIO()
    with wave.open(output,'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(24000)
        stream.writeframes(b'\0\0'*240)
    return output.getvalue()


def response(data=None, status=200, lines=None, body=None):
    result=Mock(status_code=status)
    raw = body if body is not None else json.dumps(data).encode()
    result.iter_content.return_value=[raw]
    result.iter_lines.return_value=lines or []
    return result


class NeuralVoiceTests(unittest.TestCase):
    def test_kana_is_reading_aid_and_keeps_japanese_and_numbers(self):
        self.assertEqual(anime_reading('Ciao, Aura! こんにちは。42?'),'チャオ, アウラ! こんにちは。42?')
        self.assertEqual(anime_reading('Ehi, sono Aura!'),'エイ, ソノ アウラ!')
        self.assertIn('ラッコンタメラ',anime_reading('Raccontamela.'))

    def test_qwen_joined_chunks_are_a_valid_wav(self):
        events=[{'event':'audio','audio':base64.b64encode(wav()).decode()}]*2
        with patch.object(voice,'qwen_available',return_value=True), patch.object(voice.qwen_service,'stream',return_value=(e for e in events)):
            audio=voice.generate_qwen_speech('Ciao')
        with wave.open(io.BytesIO(audio),'rb') as source:
            self.assertEqual(source.getnframes(),480)

    def test_qwen_missing_or_timed_out_is_explicit(self):
        with patch.object(voice,'qwen_available',return_value=False):
            with self.assertRaises(voice.NeuralVoiceError):voice.generate_qwen_speech('Ciao')
        with patch.object(voice,'qwen_available',return_value=True), patch.object(voice.qwen_service,'stream',side_effect=TimeoutError('secret')):
            with self.assertRaises(voice.NeuralVoiceError) as error:voice.generate_qwen_speech('Ciao')
            self.assertNotIn('secret',str(error.exception))

    def test_audio_validation_rejects_html_and_truncated_wav(self):
        for bad in (b'<html>error</html>',b'RIFF'+b'0'*60):
            with self.assertRaises(voice.NeuralVoiceError):voice.validate_wav(bad)
        self.assertEqual(voice.validate_wav(wav()),wav())

    def test_missing_token_and_long_input_never_send_network(self):
        with patch.object(voice.requests,'Session') as session:
            for token,text in (('', 'Ciao'),('hf_abcdefghijk','x'*601)):
                with self.assertRaises(voice.NeuralVoiceError):voice.generate_irodori_speech(text,token)
        session.assert_not_called()

    def test_irodori_upload_queue_and_download_use_one_fixed_host(self):
        audio=wav()
        complete=[b'event: complete',('data: '+json.dumps([{'path':'/tmp/gradio/output/audio.wav'},'log'])).encode(),b'']
        replies=[response(['/tmp/gradio/ref/audio.wav']),response({'event_id':'a'*32}),response(lines=complete),response(body=audio)]
        session=Mock();session.headers={};session.request.side_effect=replies
        with patch.object(voice.requests,'Session') as factory:
            factory.return_value.__enter__.return_value=session
            result=voice.generate_irodori_speech('Ehi, sono Aura!','hf_abcdefghijk')
        self.assertEqual(result,audio)
        self.assertFalse(session.trust_env)
        self.assertTrue(all(c.args[1].startswith(voice.IRODORI_HOST+'/') for c in session.request.call_args_list))
        self.assertTrue(all(c.kwargs['allow_redirects'] is False for c in session.request.call_args_list))
        sent=session.request.call_args_list[1].kwargs['json']['data']
        self.assertEqual(sent[0],'エイ, ソノ アウラ!')
        self.assertEqual(sent[2][0]['path'],'/tmp/gradio/ref/audio.wav')

    def test_remote_output_cannot_redirect_credentials_to_another_host(self):
        for path in ('https://evil.example/audio.wav','/etc/passwd','/tmp/gradio/'+'x'*1024):
            complete=[b'event: complete',('data: '+json.dumps([{'path':path}])).encode(),b'']
            with self.assertRaises(voice.NeuralVoiceError):voice._result_file(response(lines=complete),float('inf'))

    def test_upstream_errors_are_redacted_and_quota_is_actionable(self):
        for upstream in ('ZeroGPU quota exceeded hf_private_credential','traceback secret-test'):
            lines=[b'event: error',('data: '+json.dumps(upstream)).encode(),b'']
            with self.assertRaises(voice.NeuralVoiceError) as context:
                voice._result_file(response(lines=lines),float('inf'))
            self.assertNotIn('secret-test',str(context.exception))
            self.assertNotIn('hf_private',str(context.exception))
            if 'quota' in upstream:self.assertIn('Quota gratuita',str(context.exception))


if __name__=='__main__':unittest.main()
