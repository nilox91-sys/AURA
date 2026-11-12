from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_engine import LLMEngine
from voice_profile import voice_prosody


class CozyTests(unittest.TestCase):
    def test_personality_respects_user_and_dialect(self):
        request = 'Rispondi in italiano formale, senza battute. Spiega questa API.'
        messages, _ = LLMEngine.build_messages(request, [], {
            'personality_profile': 'cozy_nerd', 'nerd_intensity': 'enthusiastic',
            'dialect': 'napoletano', 'dialect_intensity': 'balanced',
        })
        system = messages[0]['content']
        self.assertIn('nerd cozy', system)
        self.assertIn('richieste esplicite dell’utente', system)
        self.assertIn('senza battute', system)
        self.assertIn('napoletano', system)
        self.assertIn('non hai strumenti', system)
        self.assertEqual(messages[-1], {'role': 'user', 'content': request})

    def test_neutral_personality_can_be_restored(self):
        messages, _ = LLMEngine.build_messages('Ciao', [], {'personality_profile': 'neutral'})
        self.assertNotIn('Personalità nerd cozy', messages[0]['content'])
        self.assertIn('Personalità sobria', messages[0]['content'])

    def test_voice_bounds_include_emotion_and_legacy_pitch(self):
        for character in ('cozy', 'natural'):
            for emotion in ('felice', 'triste', 'allerta', 'sorpresa', 'amore', 'unknown'):
                for pitch, rate in ((20, 20), (-35, -20)):
                    result = voice_prosody(emotion, pitch, rate, character, kawaii=True)
                    self.assertLessEqual(int(result['pitch'][:-2]), 20)
                    self.assertGreaterEqual(int(result['pitch'][:-2]), -35)
                    self.assertLessEqual(int(result['rate'][:-1]), 20)
                    self.assertGreaterEqual(int(result['rate'][:-1]), -20)

    def test_cozy_reduces_emotional_jumps(self):
        for emotion in ('felice', 'triste', 'allerta', 'sorpresa'):
            cozy = voice_prosody(emotion, 0, 0, 'cozy')
            classic = voice_prosody(emotion, 0, 0, 'natural')
            self.assertLessEqual(abs(int(cozy['pitch'][:-2])), abs(int(classic['pitch'][:-2])))
            self.assertLess(abs(int(cozy['rate'][:-1])), abs(int(classic['rate'][:-1])))


if __name__ == '__main__':
    unittest.main()
