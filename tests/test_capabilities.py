import json
import unittest
import httpx
from ollama_gui.backend import Ollama


class ModelCapabilitiesTests(unittest.IsolatedAsyncioTestCase):
    async def test_reported_capabilities_for_custom_model_names(self):
        def handle(request):
            self.assertEqual(request.url.path, '/api/show')
            self.assertEqual(request.method, 'POST')
            self.assertEqual(json.loads(request.content), {'model': 'my/custom-model:Q4'})
            return httpx.Response(200, json={'capabilities': ['completion', 'vision', 'tools']})
        caps = await Ollama('http://localhost', httpx.MockTransport(handle)).model_capabilities('my/custom-model:Q4')
        self.assertIn('vision', caps)

    async def test_text_only_or_missing_capabilities_do_not_imply_vision(self):
        for data in ({'capabilities': ['completion', 'thinking']}, {'details': {'family': 'llava'}}, {}):
            caps = await Ollama('http://localhost', httpx.MockTransport(lambda _: httpx.Response(200, json=data))).model_capabilities('vision-in-name')
            self.assertNotIn('vision', caps)

    async def test_failure_and_malformed_results_are_not_accepted(self):
        for data in ({'capabilities': 'vision'}, {'capabilities': [None]}, {'error': 'Model unavailable'}):
            with self.assertRaises((ValueError, RuntimeError)):
                await Ollama('http://localhost', httpx.MockTransport(lambda _: httpx.Response(200, json=data))).model_capabilities('test')
        with self.assertRaises(httpx.HTTPStatusError):
            await Ollama('http://localhost', httpx.MockTransport(lambda _: httpx.Response(404))).model_capabilities('missing')
