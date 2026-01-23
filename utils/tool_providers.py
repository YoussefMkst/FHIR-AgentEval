"""
Tool providers: adapt external endpoints into LangChain-compatible tools.

Includes:
- ToolProvider: minimal base
- MCPToolProvider: fetch tools from one or more MCP servers over SSE
- RESTToolProvider: wrap a FHIR REST base URL into create/read/update/delete/search tools

Notes:
- Returned tools are suitable for prebuilt agents like LangGraph's create_react_agent.
- REST tools use synchronous HTTP via `requests`; LangChain will run them in threads.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union

import requests  # type: ignore

try:
    # LangChain 0.2+ location
    from langchain.tools import StructuredTool
except Exception:  # pragma: no cover
    # Older LC fallback
    from langchain.agents import Tool as StructuredTool  # type: ignore

from langchain_mcp_adapters.client import MultiServerMCPClient


class ToolProvider:
    """Abstract provider API for LangChain tools."""

    async def get_tools(self) -> List[Any]:
        raise NotImplementedError


class MCPToolProvider(ToolProvider):
    """Load tools from one or more MCP servers over SSE.

    servers: can be
      - str: single SSE URL (default name="fhir")
      - dict: {"name": str, "url": str, "headers"?: dict}
      - list[dict|str]: multiple server entries

    If prefix_names is True, tool names will be prefixed with the server name,
    e.g., "fhir.getAllResources". This is optional (defaults to False).
    """

    def __init__(
        self,
        servers: Union[str, Dict[str, Any], Sequence[Union[str, Dict[str, Any]]]],
        *,
        prefix_names: bool = False,
    ) -> None:
        self._client_map: Dict[str, Dict[str, Any]] = self._normalize_servers(servers)
        self._prefix = prefix_names

    @staticmethod
    def _normalize_servers(
        servers: Union[str, Dict[str, Any], Sequence[Union[str, Dict[str, Any]]]]
    ) -> Dict[str, Dict[str, Any]]:
        # Normalize into MultiServerMCPClient mapping: name -> {transport:'sse', url, headers?}
        if isinstance(servers, str):
            return {"fhir": {"transport": "sse", "url": servers}}
        if isinstance(servers, dict):
            name = servers.get("name") or "fhir"
            return {name: {"transport": servers.get("transport", "sse"), "url": servers["url"], "headers": servers.get("headers")}}
        out: Dict[str, Dict[str, Any]] = {}
        for item in servers:
            if isinstance(item, str):
                out.setdefault("fhir", {"transport": "sse", "url": item})
            else:
                name = item.get("name") or "fhir"
                out[name] = {"transport": item.get("transport", "sse"), "url": item["url"], "headers": item.get("headers")}
        return out

    async def get_tools(self) -> List[Any]:
        client = MultiServerMCPClient(self._client_map)
        tools = await client.get_tools()
        if self._prefix:
            # Best-effort prefix by server name when possible
            # We do not have origin metadata per-tool; prefixing is skipped unless provided elsewhere.
            # Since origin is unavailable here, we leave as-is. Kept for future extension.
            pass
        return tools


class MultiMCPToolProvider(ToolProvider):
    """Combine tools from multiple MCP providers into a single provider."""

    def __init__(self, providers: List[MCPToolProvider]):
        self._providers = providers

    async def get_tools(self) -> List[Any]:
        """Combine tools from all providers, handling name conflicts by prefixing."""
        all_tools = []
        seen_names = set()

        for i, provider in enumerate(self._providers):
            try:
                tools = await provider.get_tools()
                print(f"[MultiMCPToolProvider] Provider {i} returned {len(tools)} tools")
                if tools:
                    tool_names = [getattr(t, "name", "unnamed") for t in tools]
                    print(f"[MultiMCPToolProvider] Provider {i} tools: {tool_names}")
                for tool in tools:
                    original_name = getattr(tool, "name", "tool")
                    # If there's a name conflict, prefix with provider index
                    if original_name in seen_names:
                        prefixed_name = f"provider_{i}_{original_name}"
                        print(f"[MultiMCPToolProvider] Renaming tool '{original_name}' to '{prefixed_name}' to avoid conflict")
                        tool.name = prefixed_name
                    else:
                        seen_names.add(original_name)
                all_tools.extend(tools)
            except Exception as e:
                print(f"[MultiMCPToolProvider] Error loading tools from provider {i}: {e}")

        print(f"[MultiMCPToolProvider] Total tools loaded: {len(all_tools)}")
        return all_tools


class RESTToolProvider(ToolProvider):
    """Wrap a FHIR REST base URL into canonical tools used by evaluators.

    Creates the following tool names to match task expectations:
      - getAllResources(resourceType: str, filters: dict|None)
      - getResourceById(resourceType: str, id: str)
      - createResource(resource: dict)
      - updateResource(resourceType: str, id: str, resource: dict)
      - deleteResource(resourceType: str, id: str)
    """

    def __init__(
        self,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout_s: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        }
        self.timeout_s = timeout_s

    def _make_get_all(self):
        base_url = self.base_url
        headers = self.headers
        timeout_s = self.timeout_s

        def getAllResources(resourceType: str, filters: Optional[Dict[str, Any]] = None) -> Any:
            """FHIR search (Bundle). Example: getAllResources("Slot", {"status": "free", "_sort": "start"})."""
            url = f"{base_url}/{resourceType}"
            resp = requests.get(url, headers=headers, params=filters or {}, timeout=timeout_s)
            ctype = resp.headers.get("content-type", "")
            return resp.json() if "json" in ctype else resp.text

        return StructuredTool.from_function(
            getAllResources,
            name="getAllResources",
            description="Search FHIR resources. Params in 'filters' map to query string.",
        )

    def _make_get_by_id(self):
        base_url = self.base_url
        headers = self.headers
        timeout_s = self.timeout_s

        def getResourceById(resourceType: str, id: str) -> Any:
            """FHIR read by id. Example: getResourceById("Slot", "SLOT001")."""
            url = f"{base_url}/{resourceType}/{id}"
            resp = requests.get(url, headers=headers, timeout=timeout_s)
            ctype = resp.headers.get("content-type", "")
            return resp.json() if "json" in ctype else resp.text

        return StructuredTool.from_function(
            getResourceById,
            name="getResourceById",
            description="Read a single FHIR resource by id.",
        )

    def _make_create(self):
        base_url = self.base_url
        headers = self.headers
        timeout_s = self.timeout_s

        def createResource(resource: Dict[str, Any]) -> Any:
            """FHIR create. Example: createResource({"resourceType":"Patient", ...})."""
            url = f"{base_url}/{resource['resourceType']}"
            resp = requests.post(url, headers=headers, json=resource, timeout=timeout_s)
            ctype = resp.headers.get("content-type", "")
            return resp.json() if "json" in ctype else resp.text

        return StructuredTool.from_function(
            createResource,
            name="createResource",
            description="Create a FHIR resource (POST).",
        )

    def _make_update(self):
        base_url = self.base_url
        headers = self.headers
        timeout_s = self.timeout_s

        def updateResource(resourceType: str, id: str, resource: Dict[str, Any]) -> Any:
            """FHIR update. Example: updateResource("Slot", "SLOT001", {...})."""
            url = f"{base_url}/{resourceType}/{id}"
            resp = requests.put(url, headers=headers, json=resource, timeout=timeout_s)
            ctype = resp.headers.get("content-type", "")
            return resp.json() if "json" in ctype else resp.text

        return StructuredTool.from_function(
            updateResource,
            name="updateResource",
            description="Update a FHIR resource by id (PUT).",
        )

    def _make_delete(self):
        base_url = self.base_url
        headers = self.headers
        timeout_s = self.timeout_s

        def deleteResource(resourceType: str, id: str) -> Any:
            """FHIR delete. Example: deleteResource("Appointment", "APPT001")."""
            url = f"{base_url}/{resourceType}/{id}"
            resp = requests.delete(url, headers=headers, timeout=timeout_s)
            ctype = resp.headers.get("content-type", "")
            # DELETE often returns empty body; return text or status
            if "json" in ctype:
                try:
                    return resp.json()
                except Exception:
                    return {"status_code": resp.status_code}
            return resp.text or {"status_code": resp.status_code}

        return StructuredTool.from_function(
            deleteResource,
            name="deleteResource",
            description="Delete a FHIR resource by id (DELETE).",
        )

    async def get_tools(self) -> List[Any]:
        # Build and return canonical FHIR REST tools
        return [
            self._make_get_all(),
            self._make_get_by_id(),
            self._make_create(),
            self._make_update(),
            self._make_delete(),
        ]


