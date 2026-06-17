# fhir_mcp_server.py — FHIR MCP server over SSE (/fhir_mcp). Works with n8n's SSE client.
# Deps:
#   pip install -U fastmcp httpx "pydantic>=2"

import os, sys, argparse, asyncio, logging, json
from typing import Any, Optional, Dict, List, Annotated

import httpx
from pydantic import Field, BaseModel, ConfigDict
from fastmcp import FastMCP

# ── logging ──────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("fhir-mcp")

# ── config ───────────────────────────────────────────────────────────
# If HAPI is published as ports ["7070:8080"], use 7070 from the host.
DEFAULT_FHIR_BASE = os.getenv("FHIR_BASE_URL", "http://localhost:7070/fhir")
mcp = FastMCP(name="fhir-basic")

# ── helpers ──────────────────────────────────────────────────────────
def base_url_or_default(base_url: Optional[str]) -> str:
    return (base_url or DEFAULT_FHIR_BASE).rstrip("/")

async def json_request(
    method: str,
    url: str,
    *,
    headers: Dict[str, str] | None = None,
    json: Any | None = None,
) -> Dict[str, Any]:
    base_headers = {"Accept": "application/fhir+json"}
    if json is not None:
        base_headers["Content-Type"] = "application/fhir+json"
    if headers:
        base_headers.update(headers)
    # TO TEST
    if method == "GET":
        base_headers["Cache-Control"] = "no-cache"

    log.debug("HTTP %s %s headers=%s", method, url, base_headers or {})
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.request(method, url, headers=base_headers, json=json)
        log.info("HTTP %s %s -> %s", method, url, resp.status_code)

        # --- CHANGED: don't raise; parse body and return structured error on non-2xx
        text = resp.text or ""
        parsed = None
        try:
            parsed = resp.json()
        except Exception:
            parsed = None

        if 200 <= resp.status_code < 300:
            return parsed if isinstance(parsed, dict) else {}

        # Build a rich error object (prefer OperationOutcome fields)
        err: Dict[str, Any] = {
            "error": "HTTP_ERROR",
            "status": resp.status_code,
            "method": method,
            "url": str(resp.request.url if resp.request else url),
        }

        if isinstance(parsed, dict) and parsed.get("resourceType") == "OperationOutcome":
            issues = parsed.get("issue", []) or []
            diagnostics = "; ".join(i.get("diagnostics", "") for i in issues if i.get("diagnostics"))
            codes = ", ".join(i.get("code", "") for i in issues if i.get("code"))
            # Optional: first offending path (if server provides it)
            first_expr = None
            for i in issues:
                expr = i.get("expression") or []
                if expr:
                    first_expr = expr[0]
                    break
            err.update({
                "error": "OPERATION_OUTCOME",
                "operationOutcome": parsed,
                "diagnostics": diagnostics or None,
                "issue_codes": codes or None,
                "issue_count": len(issues),
                "first_expression": first_expr,
            })
        else:
            # Not OO / not JSON → include a body excerpt for debugging
            err["body_excerpt"] = text[:3000]

        log.error("HTTP error %s %s: %s | %s",
                  method, url, err.get("error"), err.get("diagnostics") or err.get("body_excerpt", "")[:240])
        return err


def next_link(bundle: Dict[str, Any]) -> Optional[str]:
    for link in bundle.get("link", []) or []:
        if link.get("relation") == "next":
            return link.get("url")
    return None

# --- INTERNAL (undecorated) helper so tools don't call other tools ---
async def _get_capability_statement(base_url: Optional[str] = None) -> Dict[str, Any]:
    """Undecorated helper that actually fetches /metadata (avoid calling a FunctionTool)."""
    b = base_url_or_default(base_url)
    log.info("GET CapabilityStatement from %s", b)
    return await json_request("GET", f"{b}/metadata")

# ── optional search params validator (used only for searchResources) ─
class SearchParams(BaseModel):
    """
    Friendly names serialize as official FHIR keys via aliases:
      count -> _count, sort -> _sort, include -> _include, revinclude -> _revinclude
    """
    model_config = ConfigDict(populate_by_name=True)

    # Common clinical filters
    patient: Optional[str]    = Field(None, description="Patient logical id (e.g., '123').")
    subject: Optional[str]    = Field(None, description="Subject reference (varies by resource).")
    identifier: Optional[str] = Field(None, description="Identifier token (system|value or value).")
    code: Optional[str]       = Field(None, description="Token (often system|code), e.g., LOINC.")
    category: Optional[str]   = Field(None, description="Category token.")
    date: Optional[str]       = Field(None, description="Date or range, e.g., ge2020-01-01.")

    # Control params — publish with FHIR names via aliases
    count: Optional[int] = Field(None, alias="_count",      serialization_alias="_count",
                                 description="Page size (FHIR: _count).")
    sort: Optional[str] = Field(None, alias="_sort",        serialization_alias="_sort",
                                description="Sort rules (FHIR: _sort).")
    include: Optional[List[str]] = Field(None, alias="_include",   serialization_alias="_include",
                                         description="Repeatable include (FHIR: _include).")
    revinclude: Optional[List[str]] = Field(None, alias="_revinclude", serialization_alias="_revinclude",
                                            description="Repeatable revinclude (FHIR: _revinclude).")

# ────────────────────────────────────────────────────────────────────
# SIMPLE tools only (for n8n)
# ────────────────────────────────────────────────────────────────────

# @mcp.tool(
#     name="getCapabilities",
#     description="Fetch the FHIR CapabilityStatement (GET /metadata) from the default base URL."
# )
# async def getCapabilities() -> Dict[str, Any]:
#     """Parameterless wrapper for CapabilityStatement (uses DEFAULT_FHIR_BASE)."""
#     return await _get_capability_statement()


@mcp.tool(
    name="listResourceTypes",
    description="Return the set of resource types supported by the server (parsed from /metadata)."
)
async def listResourceTypes() -> Dict[str, List[str]]:
    """Return supported resource types (from /metadata)."""
    caps = await _get_capability_statement()
    types: List[str] = []
    for rest in (caps.get("rest") or []):
        for res in (rest.get("resource") or []):
            t = res.get("type")
            if isinstance(t, str):
                types.append(t)
    return {"resourceTypes": sorted(set(types))}



@mcp.tool(
    name="getResourceById",
    description="Read a single FHIR resource (GET /{type}/{id}) from the default base URL."
)
async def getResourceById(
    resourceType: Annotated[str, Field(description="FHIR resource type (e.g., 'Patient', 'Coverage').")],
    resourceId:   Annotated[str, Field(description="Logical resource id (e.g., '12345').")],
) -> Dict[str, Any]:
    b = base_url_or_default(None)
    url = f"{b}/{resourceType}/{resourceId}"
    log.info("getResourceById %s %s", resourceType, url)
    return await json_request("GET", url)

def _normalize_params_json(params_json: Optional[str | Dict[str, Any]]) -> Dict[str, Any]:
    """Accept params_json as dict or JSON string and return a dict.

    Rules:
      - None/""/{} -> {}
      - dict -> as-is
      - string -> json.loads and must decode to an object (dict)
      - otherwise -> ValueError with clear guidance
    """
    if params_json is None or params_json == "" or params_json == {}:
        return {}
    if isinstance(params_json, dict):
        return params_json
    if isinstance(params_json, str):
        try:
            obj = json.loads(params_json)
        except json.JSONDecodeError as e:
            raise ValueError(
                "Invalid params_json: expected a JSON object string. "
                "Example: '{\"patient\":\"123\"}'. "
                f"Details: {e}"
            )
        if not isinstance(obj, dict):
            raise ValueError(
                f"Invalid params_json: expected JSON object, got {type(obj).__name__}. "
                "Example: '{\"patient\":\"123\"}'."
            )
        return obj
    # raise ValueError(
    #     f"Invalid params_json type: {type(params_json).__name__}. "
    #     "Provide either a dict or a JSON object string."
    # )



@mcp.tool(
    name="searchResources",
    description=(
        "Search a FHIR resource type (GET /{type}?params) against the default base URL. "
        "Accepts params as a dict or JSON string; supports pagination via Bundle.link[next]."
    )
)
async def searchResources(
    resourceType: Annotated[str, Field(description="FHIR resource type (e.g., 'Patient', 'Observation').")],
    params_json:  Annotated[Optional[str | Dict[str, Any]], Field(description="FHIR search params as dict or JSON string. Examples: {\"patient\":\"123\"} or '{\"patient\":\"123\"}'. Omit or '{}' for unfiltered search.")] = None,
    all_pages:    Annotated[bool, Field(description="If true, follows Bundle.link[next] to return all pages (default: true).")] = True,
    page_limit:   Annotated[Optional[int], Field(description="Optional max number of pages to fetch when all_pages=true (safety cap).")] = None,
) -> Dict[str, Any]:
    # parse and normalize while preserving unknown keys
    raw: Dict[str, Any] = _normalize_params_json(params_json)

    normalized: Dict[str, Any] = dict(raw)  # start with everything as-is
    # Try to normalize friendly control keys to FHIR aliases; keep others intact
    try:
        sp = SearchParams.model_validate(raw)
        aliases = sp.model_dump(exclude_none=True, by_alias=True)
        # remove friendly names if present to avoid duplicates
        for friendly in ("count", "sort", "include", "revinclude"):
            normalized.pop(friendly, None)
        # overlay alias keys (_count, _sort, _include, _revinclude, etc.)
        normalized.update(aliases)
    except Exception:
        # If validator fails, just pass raw through unchanged
        pass

    import urllib.parse as _u
    b = base_url_or_default(None)

    qpairs: List[tuple[str, str]] = []
    for k, v in (normalized or {}).items():
        if isinstance(v, list):
            for item in v:
                qpairs.append((k, str(item)))
        else:
            qpairs.append((k, str(v)))
    qs = _u.urlencode(qpairs, doseq=True)
    url = f"{b}/{resourceType}" + (f"?{qs}" if qs else "")

    log.info("searchResources %s %s", resourceType, url)
    bundle = await json_request("GET", url)
    if not all_pages:
        return bundle

    # paginate
    entries = list(bundle.get("entry", []) or [])
    n_url, pages = next_link(bundle), 1
    while n_url and (page_limit is None or pages < page_limit):
        log.debug("follow next page: %s", n_url)
        page = await json_request("GET", n_url)
        entries.extend(page.get("entry", []) or [])
        n_url, pages = next_link(page), pages + 1

    bundle["entry"] = entries
    log.info("searchResources aggregated entries=%d", len(entries))
    return bundle



@mcp.tool(
    name="createResource",
    description="Create a FHIR resource (POST /{type}) at the default base URL. Body must be a JSON string."
)
async def createResource(
    resourceType: Annotated[str, Field(description="FHIR resource type (e.g., 'Coverage').")],
    body_json:    Annotated[str, Field(description="FHIR resource JSON as a string. Must include 'resourceType' that matches the path. Example: '{\"resourceType\":\"Coverage\",...}'.")],
    ifNoneExist:  Annotated[Optional[str], Field(description="Optional conditional create (HTTP 'If-None-Exist' header), e.g., 'identifier=system|value'.")] = None,
) -> Dict[str, Any]:
    # Parse body_json
    try:
        body = json.loads(body_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid body_json (must be JSON): {e}")

    # Gentle consistency check
    body_rt = body.get("resourceType")
    if body_rt and body_rt != resourceType:
        log.warning("createResource: body.resourceType=%s does not match path resourceType=%s", body_rt, resourceType)

    b = base_url_or_default(None)
    url = f"{b}/{resourceType}"
    headers = {"If-None-Exist": ifNoneExist} if ifNoneExist else None
    log.info("createResource %s %s ifNoneExist=%s", resourceType, url, bool(ifNoneExist))
    return await json_request("POST", url, headers=headers, json=body)



@mcp.tool(
    name="updateResource",
    description=(
        "PUT /{resourceType}/{id}: replace (or create if missing) the resource at specific id: {id} with the FULL JSON body."
        "Ensures body.resourceType={resourceType} and body.id={id}. "
        "Use when the id is specified; otherwise, use createResource to let the server assign one."
    )
)
async def updateResource(
    resourceType:   Annotated[str, Field(description="FHIR resource type (e.g., 'Coverage').")],
    resourceId:     Annotated[str, Field(description="Logical resource id to replace (e.g., 'COVERAGE-001').")],
    body_json:      Annotated[str, Field(description="Full replacement resource JSON as a string.")],
    ifMatchVersion: Annotated[Optional[str], Field(description='Optional ETag for optimistic concurrency, e.g., W/"5".')] = None,
) -> Dict[str, Any]:
    try:
        body = json.loads(body_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid body_json (must be JSON): {e}")

    if not isinstance(body, dict):
        raise ValueError("body_json must decode to a JSON object")
    
    body["resourceType"] = resourceType  # ensure consistency
    body["id"] = resourceId              # avoid id mismatch surprises

    b = base_url_or_default(None)
    url = f"{b}/{resourceType}/{resourceId}"
    headers = {"If-Match": ifMatchVersion} if ifMatchVersion else None
    log.info("updateResource %s %s ifMatch=%s", resourceType, url, ifMatchVersion)
    return await json_request("PUT", url, headers=headers, json=body)



@mcp.tool(
    name="deleteResource",
    description="Delete a FHIR resource (DELETE /{type}/{id}) at the default base URL."
)
async def deleteResource(
    resourceType: Annotated[str, Field(description="FHIR resource type (e.g., 'Coverage').")],
    resourceId:   Annotated[str, Field(description="Logical resource id to delete (e.g., 'COVERAGE-001').")],
) -> Dict[str, Any]:
    b = base_url_or_default(None)
    url = f"{b}/{resourceType}/{resourceId}"
    log.info("deleteResource %s %s", resourceType, url)
    return await json_request("DELETE", url)



# @mcp.tool(
#     name="upsertResource",
#     description="Create or replace a resource at a specific ID (PUT /{type}/{id}). Alias of updateResource."
# )
# async def upsertResource(
#     resourceType: Annotated[str, Field(description="FHIR resource type, e.g., Patient, Coverage")],
#     resourceId:   Annotated[str, Field(description="Desired resource id to create/replace at")],
#     body_json:    Annotated[str, Field(description="FHIR resource JSON string. If 'id' differs from resourceId, the server may override or error.")],
#     ifMatchVersion: Annotated[Optional[str], Field(description='Optional ETag for optimistic concurrency, e.g., W/"5".')] = None,
# ) -> Dict[str, Any]:
#     # Re-implement PUT directly (do NOT call another @mcp.tool)
#     try:
#         body = json.loads(body_json)
#     except json.JSONDecodeError as e:
#         raise ValueError(f"Invalid body_json (must be JSON): {e}")

#     if not isinstance(body, dict):
#         raise ValueError("body_json must decode to a JSON object")

#     # Ensure consistency
#     body["resourceType"] = resourceType
#     body["id"] = resourceId

#     b = base_url_or_default(None)
#     url = f"{b}/{resourceType}/{resourceId}"
#     headers = {"If-Match": ifMatchVersion} if ifMatchVersion else None
#     log.info("upsertResource %s %s ifMatch=%s", resourceType, url, ifMatchVersion)
#     return await json_request("PUT", url, headers=headers, json=body)

# ── self-test ────────────────────────────────────────────────────────
async def selftest(b: str) -> None:
    log.info("SELFTEST against %s", b)
    caps = await _get_capability_statement(b)
    res_types = [r.get("type") for rest in caps.get("rest", []) for r in rest.get("resource", [])]
    log.info("CapabilityStatement ok; %d resource types advertised", len(res_types))
    try:
        bundle = await searchResources("Patient", params_json=None, all_pages=False)  # type: ignore[arg-type]
        n = len(bundle.get("entry", []) or [])
        log.info("Search Patient ok; first page entries=%d", n)
    except Exception:
        log.warning("Patient search failed (maybe no Patients yet).")

# ── main ─────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true", help="Run a quick FHIR check and exit.")
    parser.add_argument("--base-url", default=DEFAULT_FHIR_BASE, help="FHIR base URL for selftest and tools.")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host for SSE.")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port for SSE.")
    parser.add_argument("--path", default="/fhir_mcp", help="HTTP path for SSE endpoint.")
    args = parser.parse_args()

    if args.selftest:
        asyncio.run(selftest(args.base_url))
        sys.exit(0)

    # Make --base-url effective for ALL tools at runtime
    DEFAULT_FHIR_BASE = args.base_url

    log.info("Starting MCP SSE server on http://%s:%d%s (FHIR=%s)",
             args.host, args.port, args.path, DEFAULT_FHIR_BASE)
    mcp.run(transport="sse", host=args.host, port=args.port, path=args.path)
