# memory_mcp_server.py — MCP server exposing READ-ONLY LTM retrieval for the Actor
# Deps: pip install -U fastmcp pydantic python-dotenv

import argparse, logging, os, json
from pathlib import Path
from typing import Annotated, List, Dict, Optional, Any
from dotenv import load_dotenv
from pydantic import Field
from fastmcp import FastMCP

from memory_stores.fhir_reflexion_memory_store import init_store, search_macro, search_micro, stats

load_dotenv()

LOG_LEVEL = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s: %(message)s"
)
log = logging.getLogger("ltm-mcp")

mcp = FastMCP(name="LTM")

# Initialize store dir on startup. we will re-init inside each call to stay fresh.
ROOT_DIR    = Path(__file__).resolve().parents[3]
INDEXES_DIR = ROOT_DIR / "environment" / "indexes" / "reflexion_faiss"
LTM_DIR = None  # Will be set from args in __main__


def _coerce_int(v: Any, default: int = 3, min_v: int = 1) -> int:
    try:
        out = int(v)
    except Exception:
        out = default
    if out < min_v:
        out = min_v
    return out


@mcp.tool(
    name="search_memory",
    description=(
        "Retrieves relevant long-term memory for planning BEFORE calling FHIR tools.\n\n"
        "Accepted inputs (any one of these):\n"
        "  1) Macro (free-text): pass `query` (string). Example: "
        "`{\"query\":\"add insurance to patient\"}`\n"
        "  2) Micro (operation-specific): pass `resource` and/or `operation`. Example: "
        "`{\"resource\":\"Coverage\",\"operation\":\"createResource\"}`\n"
        "  3) Raw JSON string: pass `raw` (string) with either of the above payloads.\n\n"
        "Optional: `k` (int or string) = number of results to return (default 3).\n\n"
        "Use this tool at the START of each trial to load helpful reflections/playbooks."
    )
)
def search_memory(
    query:     Annotated[Optional[str], Field(description="Free-text macro query. Omit if using resource/operation.")] = None,
    resource:  Annotated[Optional[str], Field(description="FHIR resource type for micro tips, e.g., 'Coverage'.")] = None,
    operation: Annotated[Optional[str], Field(description="Tool/operation name for micro tips, e.g., 'createResource'.")] = None,
    k:         Annotated[Optional[Any], Field(description="Number of results (int or numeric string), default 3.")] = None,
    raw:       Annotated[Optional[str], Field(description="Optional raw JSON string with keys like {query,...} OR {resource,operation,...}.")] = None,
) -> List[Dict]:
    """
    Flexible shim that accepts macro or micro queries and logs the raw payload.
    """
    # Always re-init to pick up new reflections added by another process
    init_store(LTM_DIR)

    # Log raw incoming args for debugging schema mismatches
    log.info("search_memory called with args: query=%r resource=%r operation=%r k=%r raw=%r",
             query, resource, operation, k, raw)

    # If client only sends a single positional string (n8n sometimes does this), it may arrive as `query`
    # or you can force it via `raw` (JSON).
    parsed = {}
    if raw:
        try:
            parsed = json.loads(raw)
            log.info("search_memory parsed raw JSON: %s", parsed)
        except Exception as e:
            log.warning("search_memory: could not parse raw JSON (%s). Treating as free-text query.", e)
            # Treat raw as the query text
            parsed = {"query": raw}

    # Merge explicit args over parsed where present
    if query is not None:
        parsed["query"] = query
    if resource is not None:
        parsed["resource"] = resource
    if operation is not None:
        parsed["operation"] = operation
    if k is not None:
        parsed["k"] = k

    # Coerce k
    kk = _coerce_int(parsed.get("k", 3), default=3, min_v=1)

    # Decide mode: macro wins if query provided; else micro if resource/operation provided
    q = parsed.get("query")
    res = parsed.get("resource")
    op = parsed.get("operation")

    if q and isinstance(q, str) and q.strip():
        log.info("search_memory dispatch → MACRO (q=%r, k=%d)", q[:80], kk)
        return search_macro(q, kk)

    # If either resource or operation is present, do micro. (Both optional to allow partial matches.)
    if (res and isinstance(res, str) and res.strip()) or (op and isinstance(op, str) and op.strip()):
        log.info("search_memory dispatch → MICRO (resource=%r, operation=%r, k=%d)", res, op, kk)
        return search_micro(resource=res, operation=op, k=kk)

    # Fallback: if nothing recognizable, just return empty with a log
    log.warning("search_memory: no valid query/resource/operation provided. Returning empty result.")
    return []


@mcp.tool(
    name="search_macro_reflections",
    description=(
        "Retrieve long-form (macro) reflections for high-level task planning. "
        "Call this BEFORE choosing tools to get general guidance relevant to your current goal. "
        "Input: `query` (string). Optional: `k` (default 3)."
    )
)
def search_macro_reflections(
    query: Annotated[str, Field(description="Free-text task/goal description, e.g., 'add insurance to patient'.")],
    k:     Annotated[int,  Field(description="Number of macro reflections to return.", ge=1)] = 3,
) -> List[Dict]:
    init_store(LTM_DIR)
    log.info("search_macro_reflections query=%r k=%d", query, k)
    return search_macro(query, k)


@mcp.tool(
    name="search_micro_tips",
    description=(
        "Retrieve micro tips tied to specific FHIR operations. "
        "Use this when you know the resource and/or tool you intend to call (e.g., Coverage + createResource). "
        "Inputs: `resource` (e.g., 'Coverage'), `operation` (e.g., 'createResource'). Optional: `k`."
    )
)
def search_micro_tips(
    resource:  Annotated[Optional[str], Field(description="FHIR resource type, e.g., 'Coverage', 'Patient'.")] = None,
    operation: Annotated[Optional[str], Field(description="Tool/operation, e.g., 'createResource', 'updateResource'.")] = None,
    k:         Annotated[int, Field(description="Number of micro tips to return (most recent first).", ge=1)] = 3,
) -> List[Dict]:
    init_store(LTM_DIR)
    log.info("search_micro_tips resource=%r operation=%r k=%d", resource, operation, k)
    return search_micro(resource=resource, operation=operation, k=k)


@mcp.tool(
    name="memory_stats",
    description="Return simple counts for debugging (number of macro/micro vectors and metadata rows)."
)
def memory_stats() -> Dict[str, int]:
    init_store(LTM_DIR)
    return stats()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8011)
    ap.add_argument("--path", default="/memory")
    ap.add_argument("--ltm-dir", help="Reflexion index subdirectory name (e.g., 'fhir_ref', 'exp_fig_2_with_spec')")
    args = ap.parse_args()

    # Set LTM_DIR from args or warn if missing
    if args.ltm_dir:
        LTM_DIR = str(INDEXES_DIR / args.ltm_dir)
    else:
        print("⚠️ WARNING: --ltm-dir not specified, using default 'fhir_ref'")
        LTM_DIR = str(INDEXES_DIR / "fhir_ref")
    
    init_store(LTM_DIR)
    log.info("🚀 Serving LTM on %s:%d%s (dir=%s)", args.host, args.port, args.path, LTM_DIR)
    mcp.run(transport="sse", host=args.host, port=args.port, path=args.path)
