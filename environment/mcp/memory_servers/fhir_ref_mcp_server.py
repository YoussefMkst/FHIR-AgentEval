# mcp_fhir_specs_server.py
# Minimal MCP server exposing per-resource FHIR specs to ANY agent:
#   - listResources(): discover which resource specs are available locally
#   - getStructureDefinition(): retrieve snapshot element defs for a resource
#   - getSearchParams(): retrieve (and filter) SearchParameters for a resource
#
# Requires:  pip install -U fastmcp "pydantic>=2"
#
# Default specs dir:  ${FHIR_SPECS_DIR} or CWD/fhir_res_ref
#
# Run:
#   python mcp_fhir_specs_server.py --dir ./fhir_res_ref --host 0.0.0.0 --port 8010 --path /fhir_specs --transport http
#
# Curl (JSON-RPC HTTP POST) examples:
#   # List resources
#   curl -s -X POST http://localhost:8010/fhir_specs \
#     -H 'Content-Type: application/json' \
#     -d '{"jsonrpc":"2.0","id":"1","method":"tools/call","params":{"name":"listResources","arguments":{}}}'
#
#   # StructureDefinition (elements) for Account
#   curl -s -X POST http://localhost:8010/fhir_specs \
#     -H 'Content-Type: application/json' \
#     -d '{"jsonrpc":"2.0","id":"2","method":"tools/call","params":{"name":"getStructureDefinition","arguments":{"resourceType":"Account"}}}'
#
#   # SearchParameters for Appointment (filter to type=date)
#   curl -s -X POST http://localhost:8010/fhir_specs \
#     -H 'Content-Type: application/json' \
#     -d '{"jsonrpc":"2.0","id":"3","method":"tools/call","params":{"name":"getSearchParams","arguments":{"resourceType":"Appointment","search_type":"date"}}}'

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Annotated

from fastmcp import FastMCP
from pydantic import Field

LOG_LEVEL = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("fhir-specs-mcp")

# ── config ───────────────────────────────────────────────────────────
# Data dirs are in environment/data/ relative to this script (which is in environment/mcp/memory_servers/)
_SCRIPT_DIR = Path(__file__).resolve().parent
_DATA_DIR = _SCRIPT_DIR.parent.parent / "data"

DEFAULT_SPEC_DIR = Path(os.getenv("FHIR_SPECS_DIR", _DATA_DIR / "fhir_res_ref_all")).resolve()

# For datatypes
DEFAULT_DT_DIR = Path(os.getenv("FHIR_DATATYPES_DIR", _DATA_DIR / "fhir_datatypes_ref")).resolve()

mcp = FastMCP(name="fhir-specs")


# ── storage & indexing ───────────────────────────────────────────────
class Store:
    """
    Loads {Resource}.json files produced by the build script and keeps:
      - case-insensitive map for resource names
      - per-resource cache
      - per-resource indices: by_path, search_by_code, search_by_type
    Auto-refreshes when files change (based on latest .json mtime in the dir).
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._case_map: Dict[str, str] = {}
        self._indexed_mtime: float = 0.0

    # ── index maintenance ────────────────────────────────────────────
    def _latest_dir_mtime(self) -> float:
        if not self.base_dir.exists():
            return 0.0
        return max((p.stat().st_mtime for p in self.base_dir.glob("*.json")), default=0.0)

    def _build_index_if_changed(self) -> None:
        cur = self._latest_dir_mtime()
        if cur == self._indexed_mtime:
            return
        self._case_map.clear()
        if self.base_dir.exists():
            for p in self.base_dir.glob("*.json"):
                self._case_map[p.stem.lower()] = p.stem
        self._indexed_mtime = cur
        log.debug("Indexed %d resources (mtime=%.0f)", len(self._case_map), cur)

    def _resolve_name(self, resource_type: str) -> Optional[str]:
        """Return canonical ResourceType (case-insensitive), or None."""
        self._build_index_if_changed()
        if resource_type in self._case_map.values():
            return resource_type
        return self._case_map.get(resource_type.lower())

    def list_resources(self) -> List[str]:
        self._build_index_if_changed()
        return sorted(self._case_map.values())

    # ── per-resource loading & indexing ──────────────────────────────
    @staticmethod
    def _index_spec(doc: Dict[str, Any]) -> None:
        """Attach indices under _idx: by_path, search_by_code, search_by_type."""
        elements = doc.get("elements") or []
        by_path: Dict[str, Dict[str, Any]] = {}
        for el in elements:
            if isinstance(el, dict):
                p = el.get("path")
                if isinstance(p, str) and p:
                    by_path[p] = el

        by_code: Dict[str, List[Dict[str, Any]]] = {}
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for sp in (doc.get("search") or []):
            if not isinstance(sp, dict):
                continue
            code = (sp.get("code") or "").lower()
            stype = (sp.get("type") or "").lower()
            if code:
                by_code.setdefault(code, []).append(sp)
            if stype:
                by_type.setdefault(stype, []).append(sp)

        doc["_idx"] = {
            "by_path": by_path,
            "search_by_code": by_code,
            "search_by_type": by_type,
        }

    def load(self, resource_type: str) -> Dict[str, Any]:
        """Load and validate one {Resource}.json; cached + indexed."""
        canonical = self._resolve_name(resource_type)
        if not canonical:
            raise FileNotFoundError(f"No spec file for resourceType '{resource_type}'")

        # return cached if available
        doc = self._cache.get(canonical)
        # if directory changed since last cache fill, force a reload
        if doc is not None and self._latest_dir_mtime() == self._indexed_mtime:
            return doc

        fp = self.base_dir / f"{canonical}.json"
        if not fp.exists():
            raise FileNotFoundError(f"Spec file missing on disk: {fp}")

        with open(fp, "r", encoding="utf-8") as f:
            doc = json.load(f)

        # Basic validation
        rt = doc.get("resourceType")
        if rt != canonical:
            raise ValueError(f"Spec mismatch: file {fp.name} resourceType='{rt}' (expected '{canonical}')")
        if not isinstance(doc.get("elements"), list):
            raise ValueError(f"Malformed spec: elements[] missing or not a list in {fp.name}")
        if not isinstance(doc.get("search"), list):
            raise ValueError(f"Malformed spec: search[] missing or not a list in {fp.name}")

        # Attach indices & cache
        self._index_spec(doc)
        self._cache[canonical] = doc
        return doc



class DataTypeStore:
    """
    Loads {DataType}.json files produced by the datatype build script and keeps:
      - case-insensitive map for dataType names
      - per-datatype cache
      - simple index: by_path (list of elements per path)
    """
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._case_map: Dict[str, str] = {}
        self._indexed_mtime: float = 0.0

    # ----- index maintenance -----
    def _latest_dir_mtime(self) -> float:
        if not self.base_dir.exists():
            return 0.0
        return max((p.stat().st_mtime for p in self.base_dir.glob("*.json")), default=0.0)

    def _build_index_if_changed(self) -> None:
        cur = self._latest_dir_mtime()
        if cur == self._indexed_mtime:
            return
        self._case_map.clear()
        if self.base_dir.exists():
            for p in self.base_dir.glob("*.json"):
                self._case_map[p.stem.lower()] = p.stem
        self._indexed_mtime = cur
        log.debug("Indexed %d datatypes (mtime=%.0f)", len(self._case_map), cur)

    def _resolve_name(self, data_type: str) -> Optional[str]:
        self._build_index_if_changed()
        if data_type in self._case_map.values():
            return data_type
        return self._case_map.get(data_type.lower())

    def list_types(self) -> List[str]:
        self._build_index_if_changed()
        return sorted(self._case_map.values())

    # ----- per-datatype loading & indexing -----
    @staticmethod
    def _index_spec(doc: Dict[str, Any]) -> None:
        # index paths as a list (future-proof for slices on complex types)
        elements = doc.get("elements") or []
        by_path: Dict[str, List[Dict[str, Any]]] = {}
        for el in elements:
            if not isinstance(el, dict):
                continue
            p = el.get("path")
            if isinstance(p, str) and p:
                by_path.setdefault(p, []).append(el)
        doc["_idx"] = {"by_path": by_path}

    def load(self, data_type: str) -> Dict[str, Any]:
        canonical = self._resolve_name(data_type)
        if not canonical:
            raise FileNotFoundError(f"No datatype file for '{data_type}'")

        doc = self._cache.get(canonical)
        if doc is not None and self._latest_dir_mtime() == self._indexed_mtime:
            return doc

        fp = self.base_dir / f"{canonical}.json"
        if not fp.exists():
            raise FileNotFoundError(f"Datatype spec missing on disk: {fp}")

        with open(fp, "r", encoding="utf-8") as f:
            doc = json.load(f)

        # Basic validation
        dt = doc.get("dataType")
        if dt != canonical:
            raise ValueError(f"Datatype mismatch: file {fp.name} dataType='{dt}' (expected '{canonical}')")
        if not isinstance(doc.get("elements"), list):
            raise ValueError(f"Malformed datatype spec: elements[] missing or not a list in {fp.name}")

        # Attach index & cache
        self._index_spec(doc)
        self._cache[canonical] = doc
        return doc


# Initializing the instances
DT_STORE = DataTypeStore(DEFAULT_DT_DIR)
STORE = Store(DEFAULT_SPEC_DIR)


# ── tools (exactly 4) ────────────────────────────────────────────────
@mcp.tool(
    name="listResources",
    description=(
        "Discover which FHIR resource specs are available locally. "
        "Returns canonical resourceType names (e.g., 'Patient', 'Appointment', 'Account') found in the specs directory. "
        "Use this to know which resourceTypes you can query with getStructureDefinition/getSearchParams. "
        "This does NOT query a live FHIR server; it only lists local spec files."
    ),
)
async def listResources() -> Dict[str, List[str]]:
    return {"resources": STORE.list_resources()}


@mcp.tool(
    name="getStructureDefinition",
    description=(
        "Retrieve the StructureDefinition *snapshot* for a resource from local per-resource JSON (no live FHIR calls). "
        "Use this to: (1) check required fields (min>0) before create/update, "
        "(2) inspect element types (incl. Reference targets), modifiers, mustSupport, and bindings, "
        "(3) guide body construction/validation and interpret OperationOutcome errors. "
        "Input: resourceType (e.g., 'Patient'). Output includes 'elements' array and small metadata."
    ),
)
async def getStructureDefinition(
    resourceType: Annotated[str, Field(description="FHIR resource type, e.g., 'Patient'.")]
) -> Dict[str, Any]:
    try:
        doc = STORE.load(resourceType)
    except Exception as e:
        raise RuntimeError(str(e))
    return {
        "resourceType": doc.get("resourceType"),
        "fhir_version": doc.get("fhir_version"),
        "source_urls": doc.get("source_urls"),
        "elementCount": len(doc.get("elements") or []),
        "elements": doc.get("elements") or [],
    }


@mcp.tool(
    name="getSearchParams",
    description=(
        "Retrieve SearchParameters for a resource from local per-resource JSON (no live FHIR calls). "
        "Use this to construct safe, legal _search queries: learn valid parameter codes, their types, comparators, "
        "reference targets, and available chains. "
        "Optional filters: 'code' (e.g., 'identifier') or 'search_type' (e.g., 'token','date','reference','string', etc.). "
        "Notes for agents:\n"
        "- token: identifiers/codes; supports forms like 'system|code', plain 'code'; may support modifiers (e.g., :not, :text)\n"
        "- string: partial match; typical modifiers include :exact and :contains\n"
        "- date/number/quantity: look at 'comparator' for eq, ne, gt, ge, lt, le, sa, eb, ap\n"
        "- reference: value can be 'ResourceType/id' or URL; 'target' tells valid referent types; 'chain' enables chained params\n"
        "- composite: requires supplying *all* components in the same query\n"
    ),
)
async def getSearchParams(
    resourceType: Annotated[str, Field(description="FHIR resource type, e.g., 'Appointment'.")],
    code: Annotated[Optional[str], Field(description="Optional: filter to a specific search code (e.g., 'identifier').")] = None,
    search_type: Annotated[Optional[str], Field(description="Optional: filter to a search type (e.g., 'token','date','reference','string','quantity','number','uri','composite','special').")] = None,
) -> Dict[str, Any]:
    try:
        doc = STORE.load(resourceType)
    except Exception as e:
        raise RuntimeError(str(e))

    if code:
        sps = doc["_idx"]["search_by_code"].get(code.lower(), [])
    elif search_type:
        sps = doc["_idx"]["search_by_type"].get(search_type.lower(), [])
    else:
        sps = doc.get("search") or []

    return {
        "resourceType": doc["resourceType"],
        "count": len(sps),
        "searchParams": sps,
    }



@mcp.tool(
    name="getDataTypeDefinition",
    description=(
        "Retrieve the StructureDefinition snapshot for a FHIR data type from local fhir_datatypes_ref. "
        "Use this to understand sub-elements of complex types (e.g., Identifier.system/value/use) or "
        "primitive constraints (e.g., code, uri). Input: dataType (e.g., 'Identifier', 'Address', 'string')."
    ),
)
async def getDataTypeDefinition(
    dataType: Annotated[str, Field(description="FHIR data type, e.g., 'Identifier', 'Address', 'string'")]
) -> Dict[str, Any]:
    try:
        doc = DT_STORE.load(dataType)
    except Exception as e:
        raise RuntimeError(str(e))
    return {
        "dataType": doc.get("dataType"),
        "typeKind": doc.get("typeKind"),
        "fhir_version": doc.get("fhir_version"),
        "source_urls": doc.get("source_urls"),
        "elementCount": len(doc.get("elements") or []),
        "elements": doc.get("elements") or [],
    }



# ── main ─────────────────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="FHIR Specs MCP Server")
    p.add_argument("--dir", default=str(DEFAULT_SPEC_DIR), help="Path to fhir_res_ref folder.")
    p.add_argument("--dt-dir", default=str(DEFAULT_DT_DIR), help="Path to fhir_datatypes_ref folder.")
    p.add_argument("--host", default="0.0.0.0", help="Bind host.")
    p.add_argument("--port", type=int, default=8010, help="Bind port.")
    p.add_argument("--path", default="/fhir_specs", help="HTTP/SSE path prefix.")
    p.add_argument("--transport", choices=["http", "sse"], default="sse", help="MCP transport. 'http' = JSON-RPC over HTTP POST.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    # rebind store to provided dir
    STORE = Store(Path(args.dir).resolve())
    log.info("Serving FHIR specs from %s", STORE.base_dir)

    DT_STORE = DataTypeStore(Path(args.dt_dir).resolve())
    log.info("Serving FHIR datatype specs from %s", DT_STORE.base_dir)

    log.info("Starting MCP on %s://%s:%d%s", args.transport, args.host, args.port, args.path)


    if args.transport == "http":
        # JSON-RPC over HTTP POST at --path
        mcp.run(transport="http", host=args.host, port=args.port, path=args.path)
    else:
        # Server-Sent Events (if your client prefers SSE)
        mcp.run(transport="sse", host=args.host, port=args.port, path=args.path)
