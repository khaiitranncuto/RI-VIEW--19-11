import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app


class GeminiTtsPreviewTests(unittest.TestCase):
    def test_preview_wraps_pcm_as_playable_wav(self):
        pcm = b'\x00\x00' * 2400
        part = SimpleNamespace(inline_data=SimpleNamespace(data=pcm))
        response = SimpleNamespace(candidates=[SimpleNamespace(
            content=SimpleNamespace(parts=[part]))])
        client = SimpleNamespace(models=SimpleNamespace(
            generate_content=lambda **kwargs: response))
        path = None
        try:
            with patch.object(app.genai, 'Client', return_value=client):
                result = app.app.test_client().post('/api/preview-gemini-tts', json={
                    'api_key': 'test-key', 'text': 'Xin chào.',
                    'voice': 'Sulafat', 'rate': '+20%',
                    'style': 'Giọng nữ Việt Nam ấm và rõ.',
                })
            self.assertEqual(result.status_code, 200)
            body = result.get_json()
            path = os.path.join(app.WORKSPACE_DIR,
                body['url'].lstrip('/').replace('/', os.sep))
            with open(path, 'rb') as audio:
                self.assertEqual(audio.read(4), b'RIFF')
        finally:
            if path and os.path.exists(path):
                os.remove(path)

    def test_preview_rejects_unknown_voice_before_calling_api(self):
        result = app.app.test_client().post('/api/preview-gemini-tts', json={
            'api_key': 'test-key', 'text': 'Xin chào.', 'voice': 'Unknown',
        })
        self.assertEqual(result.status_code, 400)
        self.assertFalse(result.get_json()['success'])


if __name__ == '__main__':
    unittest.main()
