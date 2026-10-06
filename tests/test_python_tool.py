import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path
import unittest

from ollama_gui.backend import ToolHub
from ollama_gui.python_tool import execute_python, MAX_OUTPUT_BYTES
from ollama_gui.storage import DEFAULT_SETTINGS, PYTHON_SERVER_NAME, tool_servers


@unittest.skipUnless(shutil.which("bwrap"), "bubblewrap is required")
class PythonTests(unittest.IsolatedAsyncioTestCase):
    async def test_python_file_math_and_errors(self):
        result = await execute_python("import math\nfrom fractions import Fraction\nprint(math.sqrt(81))\nprint(Fraction(1, 3) + Fraction(1, 6))", "math.py")
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(result["stdout"], "9.0\n1/2\n")
        failed = await execute_python("raise ValueError('test error')")
        self.assertNotEqual(failed["exit_code"], 0)
        self.assertIn("test error", failed["stderr"])

    async def test_private_files_environment_and_network_are_inaccessible(self):
        with tempfile.TemporaryDirectory() as root:
            secret = Path(root) / "secret.txt"
            secret.write_text("host secret")
            listener = await asyncio.start_server(lambda *_: None, "127.0.0.1", 0)
            port = listener.sockets[0].getsockname()[1]
            try:
                code = f"""import os, socket
assert not os.path.exists({str(secret)!r})
assert not os.path.exists('/home/wfo')
assert 'BRAVE_API_KEY' not in os.environ
try:
    socket.create_connection(('127.0.0.1', {port}), timeout=0.2)
except OSError:
    print('network blocked')
else:
    raise RuntimeError('Host network exposed')
"""
                result = await execute_python(code)
                self.assertEqual(result["exit_code"], 0, result["stderr"])
                self.assertEqual(result["stdout"], "network blocked\n")
            finally:
                listener.close()
                await listener.wait_closed()

    async def test_timeout_output_limit_and_validation(self):
        result = await execute_python("while True: pass", timeout_seconds=1)
        self.assertTrue(result["timed_out"], result)
        result = await execute_python("print('x' * 1000000)")
        self.assertTrue(result["output_limited"], result)
        self.assertLessEqual(len(result["stdout"].encode()) + len(result["stderr"].encode()), MAX_OUTPUT_BYTES)
        for kwargs in ({"code": ""}, {"code": "print(1)", "filename": "../outside.py"}, {"code": "print(1)", "timeout_seconds": 90}):
            with self.assertRaises(ValueError):
                await execute_python(**kwargs)

    async def test_real_mcp_execution_and_disable(self):
        servers = tool_servers(DEFAULT_SETTINGS)
        async with ToolHub(servers) as hub:
            self.assertEqual(hub.catalog[0]["name"], "execute_python")
            result = json.loads(await hub.call(hub.tools[0]["function"]["name"], {"code": "print(6 * 7)"}))
            self.assertEqual(result["stdout"], "42\n")
        async with ToolHub(tool_servers({**DEFAULT_SETTINGS, "python_enabled": False})) as hub:
            self.assertEqual(hub.tools, [])
            self.assertFalse(hub.catalog[0]["enabled"])
