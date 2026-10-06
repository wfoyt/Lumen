"""A real MCP Brave server with its HTTP upstream replaced for offline tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from ollama_gui.brave import create_server

def handle(request):
    assert request.headers["X-Subscription-Token"] == "test-only-key"
    assert request.url.params["q"]
    results = [{"title": "Test source", "url": "https://example.com/brave", "description": "Brave fixture result"}]
    return httpx.Response(200, json={"web": {"results": results}} if "/web/" in request.url.path else {"results": results})

create_server(httpx.MockTransport(handle)).run()
