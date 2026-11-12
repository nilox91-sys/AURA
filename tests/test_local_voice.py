from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_voice as voice
from voice_profile import voice_prosody
from runtime_utils import cache_audio


class LocalVoiceTests(unittest.TestCase):
    def test_invalid_style_and_speed_cannot_reach_process(self):
        with patch.object(voice.subprocess, 'run') as process:
            for style, rate in (('invalid;command', 0), ('hiyori', 99)):
                with self.assertRaises(ValueError):
                    voice.generate_local_speech('Ciao', style, rate)
        process.assert_not_called()

    def test_missing_runtime_is_explicit(self):
        with patch.object(voice, 'local_voice_available', return_value=False):
            with self.assertRaises(voice.LocalVoiceError):
                voice.generate_local_speech('Ciao')

    def test_process_uses_json_stdin_and_validates_audio(self):
        audio = b'RIFF' + b'\0' * 4 + b'WAVE' + b'\0' * 40
        with patch.object(voice, 'local_voice_available', return_value=True), \
             patch.object(voice.subprocess, 'run', return_value=Mock(stdout=audio)) as process:
            self.assertEqual(voice.generate_local_speech('Jamme, un passo alla volta.'), audio)
        self.assertNotIn('shell', process.call_args.kwargs)
        self.assertEqual(process.call_args.kwargs['timeout'], 90)
        self.assertNotIn('Jamme', ' '.join(process.call_args.args[0]))
        self.assertIn(b'Jamme', process.call_args.kwargs['input'])

    def test_bad_audio_and_process_errors_are_not_returned(self):
        with patch.object(voice, 'local_voice_available', return_value=True):
            with patch.object(voice.subprocess, 'run', return_value=Mock(stdout=b'not-wav')):
                with self.assertRaises(voice.LocalVoiceError):
                    voice.generate_local_speech('Ciao')
            with patch.object(voice.subprocess, 'run', side_effect=subprocess.TimeoutExpired('voice',90)):
                with self.assertRaises(voice.LocalVoiceError):
                    voice.generate_local_speech('Ciao')

    def test_soft_profile_does_not_add_emotional_pitch(self):
        for mood in ('normale','felice','triste','allerta','sorpresa'):
            self.assertEqual(voice_prosody(mood, 0, 0, 'soft')['pitch'], '+0Hz')

    def test_audio_cache_bounds_also_apply_to_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(201):
                (root / f'{index}.wav').write_bytes(b'wave')
            cache_audio(root / 'new.mp3', b'audio')
            self.assertLessEqual(len(list(root.iterdir())), 200)
            self.assertTrue((root / 'new.mp3').exists())


if __name__ == '__main__':
    unittest.main()
