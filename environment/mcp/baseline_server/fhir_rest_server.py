#!/usr/bin/env python3
"""
FHIR REST server for browser testing.
Standalone FastAPI server that directly calls HAPI FHIR (no MCP).
"""
import os
import json
import logging
from typing import Any, Optional, Dict, List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── logging ──────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("fhir-rest")

# ── config ───────────────────────────────────────────────────────────
DEFAULT_FHIR_BASE = os.getenv("FHIR_BASE_URL", "http://localhost:7070/fhir")

app = FastAPI(title="FHIR REST API for Testing")

# Enable CORS for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

    log.debug("HTTP %s %s", method, url)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.request(method, url, headers=base_headers, json=json)
        log.info("HTTP %s %s -> %s", method, url, resp.status_code)

        text = resp.text or ""
        parsed = None
        try:
            parsed = resp.json()
        except Exception:
            parsed = None

        if 200 <= resp.status_code < 300:
            return parsed if isinstance(parsed, dict) else {}

        # Build error object
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
            err.update({
                "error": "OPERATION_OUTCOME",
                "operationOutcome": parsed,
                "diagnostics": diagnostics or None,
                "issue_codes": codes or None,
                "issue_count": len(issues),
            })
        else:
            err["body_excerpt"] = text[:3000]

        return err

def next_link(bundle: Dict[str, Any]) -> Optional[str]:
    for link in bundle.get("link", []) or []:
        if link.get("relation") == "next":
            return link.get("url")
    return None

# ── request models ───────────────────────────────────────────────────
class GetByIdRequest(BaseModel):
    resourceType: str
    resourceId: str

class SearchRequest(BaseModel):
    resourceType: str
    params_json: Optional[Dict[str, Any]] = None
    all_pages: bool = True
    page_limit: Optional[int] = None

class CreateRequest(BaseModel):
    resourceType: str
    body_json: str
    ifNoneExist: Optional[str] = None

class UpdateRequest(BaseModel):
    resourceType: str
    resourceId: str
    body_json: str
    ifMatchVersion: Optional[str] = None

class DeleteRequest(BaseModel):
    resourceType: str
    resourceId: str

# ── endpoints ────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "ok", "message": "FHIR REST API for Testing", "fhir_base": DEFAULT_FHIR_BASE}

@app.post("/api/listResourceTypes")
async def list_resource_types():
    """Fetch supported resource types from CapabilityStatement."""
    try:
        b = base_url_or_default(None)
        result = await json_request("GET", f"{b}/metadata")
        
        types: List[str] = []
        for rest in (result.get("rest") or []):
            for res in (rest.get("resource") or []):
                t = res.get("type")
                if isinstance(t, str):
                    types.append(t)
        
        return {"resourceTypes": sorted(set(types))}
    except Exception as e:
        log.error("listResourceTypes failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/getResourceById")
async def get_resource_by_id(req: GetByIdRequest):
    """Read a single FHIR resource by type and ID."""
    try:
        b = base_url_or_default(None)
        url = f"{b}/{req.resourceType}/{req.resourceId}"
        result = await json_request("GET", url)
        return result
    except Exception as e:
        log.error("getResourceById failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/searchResources")
async def search_resources(req: SearchRequest):
    """Search FHIR resources with optional pagination."""
    try:
        b = base_url_or_default(None)
        
        # Build query string
        import urllib.parse as _u
        qpairs: List[tuple[str, str]] = []
        for k, v in (req.params_json or {}).items():
            if isinstance(v, list):
                for item in v:
                    qpairs.append((k, str(item)))
            else:
                qpairs.append((k, str(v)))
        qs = _u.urlencode(qpairs, doseq=True)
        url = f"{b}/{req.resourceType}" + (f"?{qs}" if qs else "")

        bundle = await json_request("GET", url)
        if not req.all_pages:
            return bundle

        # Paginate
        entries = list(bundle.get("entry", []) or [])
        n_url, pages = next_link(bundle), 1
        while n_url and (req.page_limit is None or pages < req.page_limit):
            log.debug("follow next page: %s", n_url)
            page = await json_request("GET", n_url)
            entries.extend(page.get("entry", []) or [])
            n_url, pages = next_link(page), pages + 1

        bundle["entry"] = entries
        log.info("searchResources aggregated entries=%d", len(entries))
        return bundle
    except Exception as e:
        log.error("searchResources failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/createResource")
async def create_resource(req: CreateRequest):
    """Create a new FHIR resource."""
    try:
        # Parse body_json
        try:
            body = json.loads(req.body_json)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

        # Check consistency
        body_rt = body.get("resourceType")
        if body_rt and body_rt != req.resourceType:
            log.warning("body.resourceType=%s != path resourceType=%s", body_rt, req.resourceType)

        b = base_url_or_default(None)
        url = f"{b}/{req.resourceType}"
        headers = {"If-None-Exist": req.ifNoneExist} if req.ifNoneExist else None
        result = await json_request("POST", url, headers=headers, json=body)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error("createResource failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/updateResource")
async def update_resource(req: UpdateRequest):
    """Update (PUT) a FHIR resource."""
    try:
        # Parse body_json
        try:
            body = json.loads(req.body_json)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object")

        # Ensure consistency
        body["resourceType"] = req.resourceType
        body["id"] = req.resourceId

        b = base_url_or_default(None)
        url = f"{b}/{req.resourceType}/{req.resourceId}"
        headers = {"If-Match": req.ifMatchVersion} if req.ifMatchVersion else None
        result = await json_request("PUT", url, headers=headers, json=body)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error("updateResource failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/deleteResource")
async def delete_resource(req: DeleteRequest):
    """Delete a FHIR resource."""
    try:
        b = base_url_or_default(None)
        url = f"{b}/{req.resourceType}/{req.resourceId}"
        result = await json_request("DELETE", url)
        return result
    except Exception as e:
        log.error("deleteResource failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# ── main ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="FHIR REST API for browser testing")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind")
    parser.add_argument("--fhir-base", default=DEFAULT_FHIR_BASE, help="FHIR server base URL")
    args = parser.parse_args()

    # Update global config
    DEFAULT_FHIR_BASE = args.fhir_base

    log.info("Starting FHIR REST server on http://%s:%d (FHIR=%s)", args.host, args.port, DEFAULT_FHIR_BASE)
    uvicorn.run(app, host=args.host, port=args.port)

