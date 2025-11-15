# mcp_base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class MCPCommand:
    """
    Represents one operation that the MCP server exposes.
    Example: name='geocode', params=['place'], description='...'
    """
    def __init__(self, name: str, params: List[str], description: str = ""):
        self.name = name
        self.params = params
        self.description = description


class MCPMapServer(ABC):
    """
    Minimal MCP-style server: has an id, a list of commands (ServerParams),
    and a unified call() method.
    """
    server_id: str = "base_server"

    @property
    @abstractmethod
    def server_params(self) -> List[MCPCommand]:
        ...

    @abstractmethod
    def call(self, command: str, **kwargs) -> Dict[str, Any]:
        """
        Execute one of the MCP commands.
        """
        ...