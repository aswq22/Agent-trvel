# app/agent/travel/mcp_utils.py
import functools
from typing import List, Optional
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agent.mcp_client import retry_interceptor, get_mcp_client
from app.config import config

# retry 2 times (spec requirement)
_travel_retry = functools.partial(retry_interceptor, max_retries=2)


async def get_travel_mcp_client(
    server_names: Optional[List[str]] = None,
) -> MultiServerMCPClient:
    """Get travel-specific MCP client (2 retries, fresh instance each call)."""
    all_servers = config.travel_mcp_servers
    if server_names:
        servers = {k: v for k, v in all_servers.items() if k in server_names}
    else:
        servers = all_servers
    return await get_mcp_client(
        servers=servers,
        tool_interceptors=[_travel_retry],
        force_new=True,
    )
