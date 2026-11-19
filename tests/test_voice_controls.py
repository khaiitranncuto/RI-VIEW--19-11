import unittest
from unittest.mock import patch, AsyncMock

import app


class VoiceControlsTests(unittest.TestCase):
    def test_main_preview_applies_current_controls(self):
        settings = dict(pitch=90, warmth=20, clarity=80, energy=75, volume=65)
        with patch('tts_engine.generate_tts_chunk_with_timing', new_callable=AsyncMock) as generate, \
                patch('voice_audio.apply_voice_settings') as apply:
            result = app.app.test_client().post('/api/preview-tts', json=dict(
                text='Xin chào.', voice='local:ngochuyen', rate='+30%', voice_settings=settings))
        data = result.get_json()
        self.assertTrue(data['success'], data)
        self.assertEqual(data['voice_settings'], settings)
        self.assertEqual(data['rate'], '+30%')
        self.assertEqual(generate.call_args.args[2], '+30%')
        self.assertEqual(apply.call_args.args[1], settings)

    def test_local_preview_also_applies_controls(self):
        with patch.object(app.subprocess, 'run'), patch('voice_audio.apply_voice_settings') as apply:
            result = app.app.test_client().post('/api/preview-local-tts', json=dict(
                text='Xin chào.', voice_settings={'pitch': 90}))
        self.assertTrue(result.get_json()['success'])
        self.assertEqual(apply.call_args.args[1]['pitch'], 90)

    def test_bad_controls_rejected(self):
        for route in ['/api/preview-tts', '/api/preview-local-tts']:
            result = app.app.test_client().post(route, json=dict(
                text='Xin chào.', voice_settings={'pitch': 101}))
            self.assertEqual(result.status_code, 400)
