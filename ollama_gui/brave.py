"""Bundled stdio MCP server for the Brave Search API; no Node runtime needed."""
import os
from pathlib import Path
from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP


async def search(kind, query, count=5, freshness="", transport=None):
    query = query.strip()
    if not query or len(query) > 600 or len(query.split()) > 75:
        raise ValueError("Use a search query of 1–600 characters and at most 75 words.")
    if not 1 <= count <= 20:
        raise ValueError("Request between 1 and 20 results.")
    if freshness not in ("", "pd", "pw", "pm", "py"):
        raise ValueError("Use pd, pw, pm or py for freshness, or leave it empty.")
    key_file = os.environ.get("BRAVE_API_KEY_FILE")
    key = Path(key_file).read_text().strip() if key_file else os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        raise ValueError("Add your Brave Search API key in Preferences, then Save Preferences.")
    params = {"q": query, "count": count}
    if freshness:
        params["freshness"] = freshness
    async with httpx.AsyncClient(timeout=30, transport=transport) as client:
        result = await client.get(f"https://api.search.brave.com/res/v1/{kind}/search", params=params, headers={"Accept": "application/json", "X-Subscription-Token": key})
    if result.is_error:
        reason = {401: "Check your API key.", 403: "Check your API key and its Search plan permissions.", 429: "The API rate limit or quota was reached. Try again later."}.get(result.status_code, "Try again later.")
        raise RuntimeError(f"Brave Search returned HTTP {result.status_code}. {reason}")
    data = result.json()
    results = data.get("web", {}).get("results", []) if kind == "web" else data.get("results", [])
    return {"query": query, "results": [{field: item[field] for field in ("title", "url", "description", "age", "page_age", "extra_snippets") if field in item} for item in results[:count]]}


def create_server(transport=None):
    server = FastMCP("Brave Search")

    @server.tool()
    async def brave_web_search(query: str, count: int = 5, freshness: Literal["", "pd", "pw", "pm", "py"] = "") -> dict:
        """Search the web with Brave. Returns source URLs and descriptions. Freshness: pd=day, pw=week, pm=month, py=year."""
        return await search("web", query, count, freshness, transport)

    @server.tool()
    async def brave_news_search(query: str, count: int = 5, freshness: Literal["", "pd", "pw", "pm", "py"] = "") -> dict:
        """Search news with Brave. Returns source URLs and descriptions. Freshness: pd=day, pw=week, pm=month, py=year."""
        return await search("news", query, count, freshness, transport)

    return server


if __name__ == "__main__":
    create_server().run()
