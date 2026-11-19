import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'local_tts/ViFastTts/src'))
from vifasttts.frontend.pipeline import parse_text
import local_pronunciation as pronunciation


class LocalPronunciationTests(unittest.TestCase):
    def test_all_configured_names_are_supported(self):
        for name in pronunciation.load_readings():
            with self.subTest(name=name):
                spoken, _, warnings = pronunciation.prepare(name, parse_text)
                self.assertTrue(pronunciation._readable(parse_text(spoken)))
                self.assertEqual(warnings, [])

    def test_vietnamese_and_punctuation_unchanged(self):
        text = 'Một nhân vật mới xuất hiện. Cậu bé chạy về nhà!'
        spoken, spans, warnings = pronunciation.prepare(text, parse_text)
        self.assertEqual(spoken, text)
        self.assertEqual(spans, [])
        self.assertEqual(warnings, [])

    def test_phrase_precedence_and_original_subtitles(self):
        spoken, spans, warnings = pronunciation.prepare('Harry Potter gặp Shizuka.', parse_text)
        self.assertEqual(spoken, 'ha ri pót tơ gặp si du ca.')
        parsed = parse_text(spoken)
        units = [dict(text=p.raw, start_ms=i*100, end_ms=(i+1)*100,
                      punctuation=p.punctuation, sentence_end=p.boundaries.sentence_end)
                 for i, p in enumerate(parsed)]
        restored = pronunciation.restore_units(units, spans)
        self.assertEqual([u['text'] for u in restored], ['Harry Potter', 'gặp', 'Shizuka'])
        self.assertEqual(restored[-1]['end_ms'], len(parsed)*100)
        self.assertTrue(restored[-1]['sentence_end'])

    def test_unknown_names_have_valid_approximation_and_warning(self):
        spoken, spans, warnings = pronunciation.prepare('Jennifer Christopher Elizabeth', parse_text)
        self.assertEqual(warnings, ['Jennifer', 'Christopher', 'Elizabeth'])
        self.assertTrue(pronunciation._readable(parse_text(spoken)))
        self.assertNotIn('tên riêng', spoken)
        self.assertEqual([s[2] for s in spans], warnings)

    def test_whole_word_match(self):
        spoken, _, _ = pronunciation.prepare('John', parse_text, {'Jo': 'giô', 'John': 'gion'})
        self.assertEqual(spoken, 'gion')

    def test_invalid_override_is_explicit_error(self):
        with self.assertRaisesRegex(ValueError, 'chưa hợp lệ'):
            pronunciation.prepare('Shizuka', parse_text, {'shizuka': 'zzzzzzz'})

    def test_config_change_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'readings.json'
            with patch.object(pronunciation, 'OVERRIDES_PATH', path):
                path.write_text(json.dumps({'John': 'gion'}), encoding='utf-8')
                first = pronunciation.cache_version()
                path.write_text(json.dumps({'John': 'giôn'}), encoding='utf-8')
                self.assertNotEqual(first, pronunciation.cache_version())


if __name__ == '__main__':
    unittest.main()
