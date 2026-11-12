from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dialect_engine import build_dialect_prompt, prepare_tts_text, dialect_metadata


class DialectTests(unittest.TestCase):
    def setUp(self):
        self.phonetics = {'global': {'API': 'a pi i'}, 'dialects': {'napoletano': {'jamme':'iamme','assaje':'assaie','nuje':'nuie'}}}

    def test_natural_voice_does_not_rewrite_text(self):
        text = 'Jamme, nuje scrivimmo API e numeri 42. Staje senza pensiere.'
        self.assertEqual(prepare_tts_text(text, 'napoletano', 'natural', self.phonetics), text)

    def test_assisted_voice_changes_only_whole_tokens(self):
        self.assertEqual(prepare_tts_text('jamme assaje nuje API jammename', 'napoletano', 'assisted', self.phonetics), 'iamme assaie nuie a pi i jammename')

    def test_code_urls_and_emails_are_protected(self):
        text = 'Jamme `API jamme` https://example.com/jamme jamme@example.com\n```python\nAPI = "jamme"\n```'
        actual = prepare_tts_text(text, 'napoletano', 'assisted', self.phonetics)
        self.assertTrue(actual.startswith('iamme '))
        self.assertIn('`API jamme`', actual)
        self.assertIn('https://example.com/jamme', actual)
        self.assertIn('jamme@example.com', actual)
        self.assertIn('API = "jamme"', actual)

    def test_assistance_does_not_translate_dialect_to_italian(self):
        text = 'Staje senza pensiere. 123,50 euro.'
        self.assertEqual(prepare_tts_text(text, 'napoletano', 'assisted', self.phonetics), text)

    def test_intensities_produce_distinct_instructions(self):
        prompts = [build_dialect_prompt('napoletano', intensity) for intensity in ('gentle','balanced','authentic')]
        self.assertEqual(len(set(prompts)), 3)
        self.assertTrue(all('Napoli' in prompt for prompt in prompts))
        self.assertTrue(all('richiesta esplicita' in prompt for prompt in prompts))

    def test_standard_does_not_inject_neapolitan_examples(self):
        self.assertNotIn('Aggio', build_dialect_prompt('standard'))

    def test_dialect_metadata_does_not_expose_internal_instructions(self):
        data = dialect_metadata()['napoletano']
        self.assertIn('previews', data)
        self.assertNotIn('guidance', data)
        self.assertGreaterEqual(len(data['sources']), 2)


if __name__ == '__main__':
    unittest.main()
