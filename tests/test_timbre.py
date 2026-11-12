import io
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import timbre_engine as engine


class TimbreTests(unittest.TestCase):
    def test_original_audio_bypasses_processing(self):
        with patch.object(engine.subprocess, 'run') as process:
            self.assertEqual(engine.apply_voice_timbre(b'original', 'none'), b'original')
        process.assert_not_called()

    def test_arbitrary_effects_are_rejected(self):
        with self.assertRaises(ValueError):
            engine.apply_voice_timbre(b'audio', 'anime; unsafe')

    def test_missing_component_is_explicit(self):
        with patch.object(engine, 'timbre_available', return_value=False):
            with self.assertRaises(engine.VoiceTimbreError):
                engine.apply_voice_timbre(b'audio', 'anime')

    def test_process_failure_hides_details_and_has_bounded_runtime(self):
        with patch.object(engine, 'timbre_available', return_value=True), \
             patch.object(engine.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'ffmpeg', stderr=b'private-details')) as process:
            with self.assertRaises(engine.VoiceTimbreError) as error:
                engine.apply_voice_timbre(b'audio', 'anime')
        self.assertNotIn('private-details', str(error.exception))
        self.assertEqual(process.call_args.kwargs['timeout'], 12)
        self.assertNotIn('shell', process.call_args.kwargs)
        self.assertEqual(process.call_args.kwargs['input'], b'audio')

    def test_real_processing_changes_pitch_without_speeding_up_audio(self):
        if not engine.timbre_available():
            self.skipTest('Optional FFmpeg rubberband not installed')
        rate = 24000
        samples = [int(0.2 * 32767 * math.sin(2 * math.pi * 440 * index / rate)) for index in range(rate)]
        raw = io.BytesIO()
        with wave.open(raw, 'wb') as wav:
            wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            wav.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
        for mode, expected in (('young', 510.4), ('anime', 541.2)):
            with self.subTest(mode=mode):
                audio = engine.apply_voice_timbre(raw.getvalue(), mode)
                decoded = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-nostdin', '-i', 'pipe:0',
                    '-f', 's16le', '-ac', '1', '-ar', str(rate), 'pipe:1'], input=audio,
                    capture_output=True, check=True, timeout=5, **engine._process_options()).stdout
                pcm = struct.unpack('<' + 'h' * (len(decoded) // 2), decoded)
                self.assertAlmostEqual(len(pcm) / rate, 1, delta=0.12)
                middle = pcm[int(.2 * rate):int(.8 * rate)]
                crosses = sum((a < 0 <= b) or (a >= 0 > b) for a, b in zip(middle, middle[1:]))
                measured = crosses / 2 / (len(middle) / rate)
                self.assertAlmostEqual(measured, expected, delta=8)
                self.assertGreater(max(abs(value) for value in pcm), 100)
                self.assertLess(max(abs(value) for value in pcm), 32767)


if __name__ == '__main__':
    unittest.main()
