"""Small adapter for NSE's official streamable-HTTP MCP server.

The UI stays usable without an internet connection because callers can fall
back to demo data.  This module intentionally only exposes raw exchange data;
it does not make recommendations.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

CM_MARKET_URL = os.getenv("NSE_MCP_URL", "https://mcp.nseindia.in/cmmkt/mcp")
BHAVCOPY_URL = "https://mcp.nseindia.in/bhavcopy/cm/mcp"


async def _call(tool_name: str, arguments: dict[str, Any], endpoint: str) -> Any:
    """Call one tool from the NSE CM-market MCP server."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    # NSE MCP currently returns 501 when a client sends the optional session
    # termination request. Closing the transport without that request is the
    # supported, quiet path for this stateless request/response use case.
    async with streamable_http_client(endpoint, terminate_on_close=False) as streams:
        # MCP 1.x returned a third callback; newer releases return two streams.
        read_stream, write_stream = streams[:2]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            parts = getattr(result, "content", [])
            text = "\n".join(getattr(part, "text", "") for part in parts)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw": text}


def call_nse_tool(tool_name: str, arguments: dict[str, Any] | None = None, endpoint: str = CM_MARKET_URL) -> Any:
    """Synchronous bridge used by Streamlit's normal execution model."""
    return asyncio.run(_call(tool_name, arguments or {}, endpoint))


def list_tools(endpoint: str = CM_MARKET_URL) -> list[str]:
    """Discover the tool names supplied by the official MCP server."""
    async def _list() -> list[str]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(endpoint, terminate_on_close=False) as streams:
            read_stream, write_stream = streams[:2]
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.list_tools()
                return [tool.name for tool in response.tools]

    return asyncio.run(_list())
