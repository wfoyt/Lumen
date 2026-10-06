import sys
from mcp.server.fastmcp import FastMCP

server = FastMCP("Test Search", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8000)

@server.tool()
def search(query: str) -> str:
    """Search the test index."""
    return f"Result for {query}: https://example.com/source"

if __name__ == "__main__":
    server.run(transport="streamable-http" if len(sys.argv) > 1 else "stdio")
