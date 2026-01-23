from abc import ABC, abstractmethod
import time
from typing import Dict, Any, List, Optional, Tuple
import requests  # type: ignore
from dataclasses import dataclass
import json
import logging
import re
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    execution_success: bool = False
    response_msg: Optional[str] = None
    token_total: Optional[int] = None
    input_query: Optional[str] = None
    total_exec_ms: Optional[float] = None
    tool_order: Optional[list[str]] = None
    tool_exec_ms: Optional[Dict[str, float]] = None
    tool_calls: Optional[Dict[str, list[Dict[str, Any]]]] = None
    tool_call_counts: Optional[Dict[str, int]] = None
    


@dataclass
class TaskResult:
    task_success: Optional[bool] = False
    assertion_error_message: Optional[str] = None
    task_id: Optional[str] = None
    task_name: Optional[str] = None
    execution_result: Optional[ExecutionResult] = None
    


@dataclass
class TaskFailureMode:
    incorrect_tool_selection: Optional[bool] = None
    incorrect_tool_order: Optional[bool] = None
    incorrect_resource_type: Optional[bool] = None
    prohibited_tool_used: Optional[bool] = None
    error_codes: Optional[List[str]] = None # https://build.fhir.org/codesystem-assert-response-code-types.html
    # Proximity metrics (0..1), advisory only
    sequence_lcs_ratio_max: Optional[float] = None
    multiset_jaccard_max: Optional[float] = None
    multiset_f1_max: Optional[float] = None



class TaskInterfaceModular(ABC):
    def __init__(self,
                fhir_server_url,
                required_tool_call_sets=None,
                required_resource_types=None,
                prohibited_tools=None,
                difficulty_level=None,
                template_params: Optional[Dict[str, Any]] = None):

        self.FHIR_SERVER_URL = fhir_server_url
        # Eval parameters
        self.required_tool_call_sets = required_tool_call_sets or []
        self.required_resource_types = required_resource_types or []
        self.prohibited_tools = prohibited_tools or []
        self.difficulty_level = difficulty_level
        
        logger.debug(f"INIT: {required_tool_call_sets=}, {required_resource_types=}, {prohibited_tools=}")
        logger.debug(f"FHIR_SERVER_URL: {self.FHIR_SERVER_URL}")
        
        self.HEADERS = {
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
            "Cache-Control": "no-cache" #just added, TEST IT OUT
        }

        self.RESOURCE_TYPES = [
            "Patient",
            "Condition",
            "Procedure",
            "Coverage",
            "Practitioner",
            "Organization",
            "RelatedPerson",
            "Consent",
            "DocumentReference",
            "Slot",
            "Schedule",
            "Appointment",
        ]
        
        # --- Template parameters (optional) -----------------------------------------
        # Tasks can declare a parameter schema via get_param_schema().
        # When provided, 'template_params' are validated/merged with defaults.
        self.template_params: Dict[str, Any] = {}
        if template_params:
            try:
                self.set_params(template_params)
            except Exception as e:
                logger.error(f"Template params validation failed: {e}")
                raise

    # -------------------------
    # Parameter templating API
    # -------------------------
    def get_param_schema(self) -> Dict[str, Any]:
        """
        Return a JSON-schema-like dictionary describing template parameters.
        Default is an empty schema (no parameters required).

        Example shape:
        {
            "type": "object",
            "required": ["patient_family", "patient_given"],
            "properties": {
                "patient_family": {"type": "string", "description": "Family name", "examples": ["Doe"], "default": "Doe"},
                "patient_given":  {"type": "string", "description": "Given name",  "examples": ["John"], "default": "John"},
                "birth_date":     {"type": "string", "description": "YYYY-MM-DD",  "pattern": "^\\d{4}-\\d{2}-\\d{2}$"}
            }
        }
        """
        return {"type": "object", "properties": {}, "required": []}

    def set_params(self, params: Dict[str, Any]) -> None:
        """Validate against schema, merge defaults, and set self.template_params.

        Lightweight checks only (no external jsonschema dependency):
        - Fill property defaults
        - Enforce 'required'
        - Validate 'enum' and 'pattern' (if provided)
        - Minimal type checks for common JSON Schema types
        """
        schema = self.get_param_schema() or {}
        props: Dict[str, Any] = schema.get("properties", {}) or {}
        required: List[str] = schema.get("required", []) or []

        merged: Dict[str, Any] = {}
        # 1) Start with defaults from schema
        for name, spec in props.items():
            if isinstance(spec, dict) and "default" in spec:
                merged[name] = spec.get("default")

        # 2) Overlay provided params
        for k, v in (params or {}).items():
            merged[k] = v

        # 3) Required checks
        missing = [r for r in required if r not in merged or merged.get(r) is None]
        if missing:
            raise ValueError(f"Missing required template params: {missing}")

        # 3.5) Gentle coercions for convenience before strict type checks
        # If a field is declared as array of strings but YAML provided a single string,
        # coerce it to a single-item list to keep schemas FHIR-aligned yet user-friendly.
        for name, spec in props.items():
            if name not in merged:
                continue
            if not isinstance(spec, dict):
                continue
            if spec.get("type") == "array":
                items_spec = spec.get("items")
                if isinstance(items_spec, dict) and items_spec.get("type") == "string":
                    val = merged.get(name)
                    if isinstance(val, str):
                        merged[name] = [val]

        # 4) Enum/pattern/type checks
        for name, spec in props.items():
            if name not in merged:
                continue
            val = merged.get(name)
            if not isinstance(spec, dict):
                continue

            # enum
            enum_vals = spec.get("enum")
            if enum_vals is not None and val is not None and val not in enum_vals:
                raise ValueError(f"Invalid value for '{name}': {val} not in enum {enum_vals}")

            # pattern (strings only)
            pattern = spec.get("pattern")
            if pattern and isinstance(val, str):
                try:
                    if re.fullmatch(pattern, val) is None:
                        raise ValueError(f"Value for '{name}' does not match pattern {pattern}")
                except re.error:
                    # Ignore invalid regex patterns in schema
                    pass

            # minimal type checks (best-effort)
            typ = spec.get("type")
            if typ and val is not None:
                type_ok = True
                if typ == "string":
                    type_ok = isinstance(val, str)
                elif typ == "integer":
                    type_ok = isinstance(val, int) and not isinstance(val, bool)
                elif typ == "number":
                    type_ok = (isinstance(val, int) or isinstance(val, float)) and not isinstance(val, bool)
                elif typ == "boolean":
                    type_ok = isinstance(val, bool)
                elif typ == "object":
                    type_ok = isinstance(val, dict)
                elif typ == "array":
                    type_ok = isinstance(val, list)
                # Custom types (e.g., 'date') are not enforced here
                if not type_ok:
                    raise ValueError(f"Invalid type for '{name}': expected {typ}, got {type(val).__name__}")

        self.template_params = merged

    def get_param(self, name: str, default: Any = None) -> Any:
        """Safe getter for a template parameter value."""
        return self.template_params.get(name, default)

    def has_param(self, name: str) -> bool:
        """True if parameter exists and is not None."""
        return name in self.template_params and self.template_params[name] is not None

    def render_prompt(self, template: str) -> str:
        """Format a prompt template using current params; leave unknown {placeholders} intact."""
        class SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"
        return template.format_map(SafeDict(self.template_params))

    def get_expected_params(self) -> Dict[str, Any]:
        """
        Return a simplified dict describing expected parameters (LLM-friendly).
        Derived tasks should override get_param_schema(); this flattens it.
        """
        schema = self.get_param_schema() or {}
        props: Dict[str, Any] = schema.get("properties", {}) or {}
        req = set(schema.get("required", []) or [])
        out: Dict[str, Any] = {}
        for name, spec in props.items():
            if not isinstance(spec, dict):
                continue
            out[name] = {
                "type": spec.get("type"),
                "description": spec.get("description"),
                "required": name in req,
                "default": spec.get("default"),
                "examples": spec.get("examples"),
                "enum": spec.get("enum"),
                "pattern": spec.get("pattern"),
            }
        return out

    def get_resource_ids(self, resource_type):
        """Fetches all resource IDs for the given resource type, handling pagination."""
        url = f"{self.FHIR_SERVER_URL}/{resource_type}?_count=1000"
        resource_ids = []
        while url:
            response = requests.get(url, headers=self.HEADERS)
            if response.status_code != 200:
                logger.error(f"Failed to fetch {resource_type}: {response.status_code}")
                break
            
            data = response.json()
            if "entry" in data:
                resource_ids.extend([entry["resource"]["id"] for entry in data["entry"]])

            # Find the next page URL
            next_url = None
            if "link" in data:
                for link in data["link"]:
                    if link["relation"] == "next":
                        next_url = link["url"]
                        break

            url = next_url  # continue if next page exists, else break the loop
        return resource_ids
        

    def delete_resource(self, resource_type, resource_id):
        """Deletes a specific resource by ID, removing any references to it first.
        recursively delete all resources that reference the resource_id
        """
        # Find any resources that reference this one
        url = f"{self.FHIR_SERVER_URL}/{resource_type}/{resource_id}"
        rev_url = f"{self.FHIR_SERVER_URL}/{resource_type}?_id={resource_id}&_revinclude:iterate=*"
        response = requests.get(rev_url, headers=self.HEADERS)
        if response.status_code != 200:
            logger.error(f"Failed to revinclude for {url}")
            logger.error(response.json())
            return
        bundle = response.json()
        entries = bundle.get("entry", [])
        for entry in entries:
            child = entry["resource"]
            child_type = child["resourceType"]
            child_id = child["id"]
            if f"{child_type}/{child_id}" != f"{resource_type}/{resource_id}":  # avoid self-reference
                self.delete_resource(child_type, child_id)
        
        # Now delete the resource itself
        del_response = requests.delete(url, headers=self.HEADERS)
        logger.debug(f"DELETE {url}: {del_response.status_code}")
        time.sleep(0.1)  # avoid overwhelming the server
        
        
    def delete_all_resources(self):
        """Deletes all resources of the specified types in the correct order to handle dependencies."""
        # Define the order of deletion based on dependencies
        # Resources that depend on others should be deleted first
        # Not necessary b/c delete_resource handles dependencies
        # But it is more efficient to delete in this order.
        deletion_order = [
            "Appointment",      # Depends on Patient, Practitioner, Location, Slot
            "Slot",            # Depends on Schedule
            "Schedule",        # Depends on Practitioner
            "DocumentReference", # Depends on Patient, Practitioner
            "Consent",         # Depends on Patient, Organization, DocumentReference
            "Account",         # Depends on Patient, RelatedPerson
            "RelatedPerson",   # Depends on Patient
            "Coverage",        # Depends on Patient, Organization
            "Procedure",       # Depends on Patient
            "Condition",       # Depends on Patient
            "ServiceRequest",  # Depends on Patient
            "CarePlan",        # Depends on Patient, Encounter
            "Location",        # No dependencies
            "Organization",    # No dependencies
            "Patient",         # No dependencies
            "Practitioner",    # No dependencies
            "DiagnosticReport",
            "FamilyMemberHistory" # No dependencies
        ]

        for resource_type in deletion_order:
            logger.debug(f"\nProcessing {resource_type} resources...")
            resource_ids = self.get_resource_ids(resource_type)

            if not resource_ids:
                logger.debug(f"No {resource_type} resources found.")
                continue

            logger.debug(f"Deleting {len(resource_ids)} {resource_type} resources...")
            for resource_id in resource_ids:
                self.delete_resource(resource_type, resource_id)
                # Add a small delay to prevent overwhelming the server
                time.sleep(0.1)
    

    def post_to_fhir(self,resource):
        """
        Posts a FHIR resource to the FHIR server.
        """
        url = f"{self.FHIR_SERVER_URL}/{resource['resourceType']}"
        headers = {
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        }
        response = requests.post(url, json=resource, headers=headers)

        if response.status_code in [200, 201]:
            return response
        else:
            raise ValueError(
                f"Failed to create {resource['resourceType']}: {response.text}"
            )
            

    def upsert_to_fhir(self,resource):
        """
        Creates or updates a FHIR resource on the FHIR server with a specified ID.
        """
        url = f"{self.FHIR_SERVER_URL}/{resource['resourceType']}/{resource['id']}"
        headers = {
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        }
        response = requests.put(url, json=resource, headers=headers)

        if response.status_code in [200, 201]:
            logger.debug(
                f"Successfully upserted {resource['resourceType']} with ID {resource['id']}"
            )
            return response
        else:
            logger.error(
                f"Failed to upsert {resource['resourceType']} with ID {resource['id']}: {response.status_code} {response.text}"
            )
            raise RuntimeError(f"{response.status_code} – {response.text}")
            #return response
            

    @abstractmethod
    def get_task_id(self) -> str:
        """Return the task ID"""
        pass


    @abstractmethod
    def get_task_name(self) -> str:
        """Return the task name"""
        pass


    @abstractmethod
    def get_prompt(self) -> str:
        """Return the prompt for the task"""
        pass


    @abstractmethod
    def prepare_test_data(self) -> None:
        """Prepare any necessary FHIR resources for the test"""
        pass


    def cleanup_test_data(self) -> None:
        """Clean up any test data created during the test"""
        self.delete_all_resources()


    @abstractmethod
    def execute_human_agent(self) -> ExecutionResult:
        """Execute the expected actions that a human should perform"""
        pass



    def get_json_from_response_msg(self, response_msg: str) -> Optional[Dict[str, Any]]:
        """Parse the JSON part in the string"""
        try:
            # Find the first occurrence of '{' and the last occurrence of '}'
            start = response_msg.index('{')
            end = response_msg.rindex('}') + 1
            json_str = response_msg[start:end]
            return json.loads(json_str)
        except (ValueError, json.JSONDecodeError):
            logger.error("Failed to parse JSON from response message.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while parsing JSON: {str(e)}")
            return None
    



    def check_tool_calls(
        self,
        task_result: TaskResult,
        required_tool_call_sets: List[Dict[str, Optional[int]]],
        required_resource_types: List[str],
        prohibited_tools: Optional[List[str]] = None,
        ) -> TaskFailureMode | None:
        """
        Failure analysis with tri‑state flags
        ------------------------------------
        False → check performed & passed | True → check performed & failed | None → not evaluated

        Flags returned in `TaskFailureMode`
        -----------------------------------
        • prohibited_tool_used     – any disallowed tool called  
        • incorrect_tool_selection – missing required tool(s)  
        • incorrect_tool_order     – required tools out of order  
        • incorrect_resource_type  – wrong resource types  
        • error_codes              – list captured from execution

        Steps
        -----
        1.  Iterate `required_tool_call_sets` until a template’s selection & order both pass.  
        2.  If (1) passes, verify resource types & capture error codes.  
        3.  Independently flag `prohibited_tool_used` without altering other flags.  
        4.  Return `None` on overall task success; otherwise a populated `TaskFailureMode`.
        Given a TaskResult (which wraps an ExecutionResult) decide *why* a task failed.

        Template formats supported (backward compatible):
        - New: { "sequence": ["tool1", "tool2", "tool1"] } → ordered subsequence with duplicates
        - Legacy: { "toolName": index or None, ... } → presence and optional relative order

        The logic tries every template in the list until one matches:

            1.  Every tool mentioned in the template must appear in `execution_result.tool_order`
                → otherwise `incorrect_tool_selection` stays True and we try the next template.

            2.  If the template has *ordered* tools (values that are integers) they must appear
                as a subsequence in `tool_order` in the given order.  
                Example: required order `["A","B","C"]` is satisfied by  
                `"B A D B A C F"` because `A … B … C` exists.

            3.  Only after (1) **and** (2) succeed do we check resource types and error codes.
        """
        # --- Fast exit ------------------------------------------------------------------
        if task_result.execution_result is None:
            return None

        exec_res: ExecutionResult = task_result.execution_result
        tool_order: List[str] = exec_res.tool_order or []
        tool_counts: Counter = Counter(tool_order)

        # --- Initialise flags -----------------------------------------------------------
        prohibited_tool_used      : Optional[bool] = None
        incorrect_tool_selection  : Optional[bool] = None
        incorrect_tool_order      : Optional[bool] = None
        incorrect_resource_type   : Optional[bool] = None
        error_codes = None

        # Proximity metrics (max across templates)
        best_lcs_ratio: Optional[float] = None
        best_jaccard: Optional[float] = None
        best_f1: Optional[float] = None

        # Helpers
        def lcs_ratio(required_seq: List[str], observed_seq: List[str]) -> float:
            if not required_seq:
                return 1.0
            n = len(required_seq)
            m = len(observed_seq)
            # DP table
            dp = [[0] * (m + 1) for _ in range(n + 1)]
            for i in range(1, n + 1):
                a = required_seq[i - 1]
                for j in range(1, m + 1):
                    b = observed_seq[j - 1]
                    if a == b:
                        dp[i][j] = dp[i - 1][j - 1] + 1
                    else:
                        left = dp[i][j - 1]
                        up = dp[i - 1][j]
                        dp[i][j] = left if left >= up else up
            lcs_len = dp[n][m]
            return float(lcs_len) / float(n)

        def jaccard_counts(req: Counter, pred: Counter) -> float:
            if not req and not pred:
                return 1.0
            inter = 0
            union = 0
            keys = set(req.keys()) | set(pred.keys())
            for k in keys:
                inter += min(req.get(k, 0), pred.get(k, 0))
                union += max(req.get(k, 0), pred.get(k, 0))
            return (float(inter) / float(union)) if union > 0 else 1.0

        def f1_counts(req: Counter, pred: Counter) -> float:
            # Micro F1 over counts
            tp = 0
            pred_sum = 0
            req_sum = 0
            keys = set(req.keys()) | set(pred.keys())
            for k in keys:
                rc = req.get(k, 0)
                pc = pred.get(k, 0)
                tp += min(rc, pc)
                pred_sum += pc
                req_sum += rc
            fp = pred_sum - tp
            fn = req_sum - tp
            precision = (tp / (tp + fp)) if (tp + fp) > 0 else (1.0 if (tp + fp + fn) == 0 else 0.0)
            recall = (tp / (tp + fn)) if (tp + fn) > 0 else (1.0 if (tp + fp + fn) == 0 else 0.0)
            if precision + recall == 0:
                return 0.0
            return 2.0 * precision * recall / (precision + recall)

        # --- 1) Match templates & compute proximity metrics -----------------------------
        for template in required_tool_call_sets:
            logger.debug(f"analysing template → {template}")
            # Normalize template into ordered sequence (if any) and required bag
            ordered_required: List[str] = []
            bag_required: Counter = Counter()

            if isinstance(template, dict) and "sequence" in template:
                seq = template.get("sequence") or []
                if isinstance(seq, list):
                    ordered_required = [str(x) for x in seq]
                    bag_required = Counter(ordered_required)
            elif isinstance(template, dict):
                # legacy mapping: tool -> index (int) or None
                # ordered part: sort items with int indices
                ordered_pairs = [(t, idx) for t, idx in template.items() if isinstance(idx, int)]
                ordered_pairs.sort(key=lambda x: x[1])
                ordered_required = [t for t, _ in ordered_pairs]
                # bag: each listed tool required at least once
                for t in template.keys():
                    bag_required[t] += 1

            # Proximity metrics for this template
            if bag_required:
                jac = jaccard_counts(bag_required, tool_counts)
                best_jaccard = jac if best_jaccard is None or jac > best_jaccard else best_jaccard
                f1v = f1_counts(bag_required, tool_counts)
                best_f1 = f1v if best_f1 is None or f1v > best_f1 else best_f1
            if ordered_required:
                lcsr = lcs_ratio(ordered_required, tool_order)
                best_lcs_ratio = lcsr if best_lcs_ratio is None or lcsr > best_lcs_ratio else best_lcs_ratio

            # -------- selection check (counts-aware when possible) --------
            selection_ok = False
            if bag_required:
                selection_ok = all(tool_counts.get(t, 0) >= c for t, c in bag_required.items())
            elif isinstance(template, dict):
                # fallback: presence-only
                selection_ok = all(t in tool_order for t in template)
            else:
                selection_ok = False

            if not selection_ok:
                logger.debug("missing required tools (or counts), trying next template")
                continue
            incorrect_tool_selection = False
            logger.debug("all required tools present (counts-aware)")

            # -------- order check --------
            if ordered_required:
                # subsequence check (duplicates handled naturally)
                want = 0
                for t in tool_order:
                    if t == ordered_required[want]:
                        want += 1
                        if want == len(ordered_required):
                            incorrect_tool_order = False
                            logger.debug(f"order satisfied → {ordered_required}")
                            break
                if incorrect_tool_order is None:
                    incorrect_tool_order = True
                    logger.debug(f"order NOT satisfied → {ordered_required}")
            else:
                incorrect_tool_order = False
                logger.debug("template has no order constraints — automatically OK")

            # stop when both checks passed
            if incorrect_tool_selection is False and incorrect_tool_order is False:
                break

        # if no template matched at all
        if incorrect_tool_selection is None:
            incorrect_tool_selection = True
            logger.debug("no template matched — selection failed")

        # --- 2) Resource/type & error codes --------------------------------------------
        if incorrect_tool_selection is False:
            error_codes, res_types = self.get_error_codes(exec_res)
            incorrect_resource_type = not all(rt in res_types for rt in required_resource_types)
            logger.debug(f"resource types seen → {res_types}")
            logger.debug(f"error codes captured → {error_codes}")

        # --- 3) Prohibited‑tool scan ----------------------------------------------------
        if prohibited_tools is not None:
            prohibited_tool_used = False
            for bad in prohibited_tools:
                if bad in tool_order:
                    prohibited_tool_used = True
                    logger.debug(f"prohibited tool used → {bad}")
                    break

        # --- 4) Return structured result -----------------------------------------------
        return TaskFailureMode(
            prohibited_tool_used     = prohibited_tool_used,
            incorrect_tool_selection = incorrect_tool_selection,
            incorrect_tool_order     = incorrect_tool_order,
            incorrect_resource_type  = incorrect_resource_type,
            error_codes              = error_codes,
            sequence_lcs_ratio_max   = best_lcs_ratio,
            multiset_jaccard_max     = best_jaccard,
            multiset_f1_max          = best_f1,
        )
    

    # Add return type hint
    def get_error_codes(self, executionResult: ExecutionResult):
        """Extract error info and resource types from tool calls (MCP + legacy)."""
        error_codes: List[str] = []
        resource_types: List[str] = []

        if not executionResult or not executionResult.tool_calls:
            return error_codes, resource_types

        # Recognize both MCP tool names and legacy placeholders for compatibility
        known_tools = {
            'createResource', 'updateResource', 'deleteResource',
            'upsertResource', 'searchResources', 'getResourceById',
            # legacy aliases sometimes seen in logs
            'getAllResources', 'getResource',
        }

        def safe_get(d: Any, *path: str) -> Any:
            cur = d
            for key in path:
                if not isinstance(cur, dict) or key not in cur:
                    return None
                cur = cur[key]
            return cur

        def parse_json_maybe(text: Any) -> Any:
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return None
            return text if isinstance(text, dict) else None

        def extract_resource_type(tool_name: str, call: Dict[str, Any]) -> str | None:
            # Prefer explicit input.resourceType (MCP shape)
            inp = call.get('input') or call.get('args') or {}
            rt = None
            if isinstance(inp, dict):
                rt = inp.get('resourceType') or inp.get('resource_type')
                if not rt and tool_name in {'createResource', 'updateResource', 'upsertResource'}:
                    body_json = inp.get('body_json')
                    body = parse_json_maybe(body_json)
                    if isinstance(body, dict):
                        rt = body.get('resourceType')
            if rt:
                return str(rt)

            # Fallback to output resourceType when a single resource was returned
            out = call.get('output')
            out_obj = parse_json_maybe(out)
            if isinstance(out_obj, dict):
                # If a Bundle, infer from search input; otherwise use resourceType directly
                out_rt = out_obj.get('resourceType')
                if isinstance(out_rt, str) and out_rt != 'Bundle':
                    return out_rt
                # Bundle fallback: try to infer from first entry
                entries = out_obj.get('entry') or []
                if isinstance(entries, list) and entries:
                    first = entries[0]
                    res = safe_get(first, 'resource')
                    if isinstance(res, dict):
                        frt = res.get('resourceType')
                        if isinstance(frt, str):
                            return frt
            return None

        try:
            # Iterate by tool then over its calls (latest-first still covered by full scan)
            for tool_name, calls in (executionResult.tool_calls or {}).items():
                if tool_name not in known_tools:
                    continue
                if not isinstance(calls, list):
                    continue
                for call in calls:
                    if not isinstance(call, dict):
                        continue

                    # Collect resource type when we can
                    rt = extract_resource_type(tool_name, call)
                    if isinstance(rt, str):
                        resource_types.append(rt)

                    # Changed this part: double check
                    # Collect error strings and OperationOutcome details
                    out_raw = call.get("output")

                    # Always try to parse (output may be a JSON string)
                    out_obj = parse_json_maybe(out_raw)

                    if isinstance(out_obj, dict):
                        # 1) Native HAPI OperationOutcome
                        if out_obj.get("resourceType") == "OperationOutcome":
                            issues = (out_obj.get("issue") or [])
                            for iss in issues:
                                details = (iss.get("details") or {}).get("text")
                                diag = iss.get("diagnostics")
                                code = iss.get("code")
                                if isinstance(details, str):
                                    error_codes.append(details)
                                elif isinstance(diag, str):
                                    error_codes.append(diag)
                                elif isinstance(code, str):
                                    error_codes.append(code)

                        # 2) MCP-wrapped OperationOutcome
                        elif out_obj.get("error") == "OPERATION_OUTCOME":
                            oo = out_obj.get("operationOutcome") or {}
                            issues = (oo.get("issue") or [])
                            if issues:
                                for iss in issues:
                                    details = (iss.get("details") or {}).get("text")
                                    diag = iss.get("diagnostics")
                                    code = iss.get("code")
                                    if isinstance(details, str):
                                        error_codes.append(details)
                                    elif isinstance(diag, str):
                                        error_codes.append(diag)
                                    elif isinstance(code, str):
                                        error_codes.append(code)
                            else:
                                # fallback to aggregated diagnostics from MCP
                                diag = out_obj.get("diagnostics")
                                if isinstance(diag, str):
                                    error_codes.append(diag)

                        # 3) Other structured MCP errors (e.g., HTTP_ERROR)
                        elif out_obj.get("error"):
                            msg = out_obj.get("diagnostics") or out_obj.get("body_excerpt")
                            if isinstance(msg, str) and msg:
                                error_codes.append(msg)

                    else:
                        # Non-JSON string → keep it as an error message
                        if isinstance(out_raw, str) and out_raw.strip():
                            error_codes.append(out_raw.strip())

        except Exception as e:
            logger.error(f"get_error_codes: unexpected error: {e}")

        return error_codes, resource_types
       
            
    
    
    @abstractmethod
    def validate_response(self, executionResult: ExecutionResult) -> TaskResult:
        """Validate the response using assertions"""
        pass
    

    # -----------------------------
    # Benchmark-aware validation
    # -----------------------------
    def is_feasible(self) -> tuple[Optional[bool], str]:
        """Run the human benchmark and return (feasible, message).

        feasible tri-state semantics:
        - True  → benchmark succeeded; params feasible
        - False → benchmark ran and indicates infeasible
        - None  → transient/unknown error; do not classify as infeasible
        """
        try:
            bench = self.execute_human_agent()
            exec_success = getattr(bench, "execution_success", False)
            response_msg = getattr(bench, "response_msg", "")
            feasible: Optional[bool] = bool(exec_success)
            return feasible, response_msg
        except Exception as e:
            # Treat likely transient errors as unknown feasibility (None)
            msg = str(e)
            lowered = msg.lower()
            looks_transient = (
                "timeout" in lowered or
                "connection" in lowered or
                "refused" in lowered or
                "unreachable" in lowered or
                "reset" in lowered or
                "dns" in lowered or
                "service unavailable" in lowered or
                "503" in lowered
            )
            if looks_transient:
                return None, msg
            return False, msg

    def validate_response_with_benchmark(self, execution_result: ExecutionResult) -> TaskResult:
        """Tri-state validation using the human benchmark for feasibility.

        task_success semantics:
        - True  → agent succeeded on a feasible task
        - False → agent failed on a feasible task
        - None → benchmark deems task infeasible (do not penalize agent)
        """
        feasible, bench_msg = self.is_feasible()
        if feasible is False:
            return TaskResult(
                task_success=None,
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
                assertion_error_message=(bench_msg or "Benchmark infeasible for given parameters"),
            )
        # Feasible or unknown (transient) → fall back to task-specific validator
        return self.validate_response(execution_result)

    
    def validate_response_light(self, execution_result: ExecutionResult) -> TaskResult:
        """
        Light validation: checks if required resource was created with key fields populated,
        without validating actual values.
        
        By default returns task_success=None to indicate light validation is not applicable.
        Override this method in creation tasks to provide light validation logic.
        
        Light validation should:
        - Query FHIR server for the resource (same as validate_response)
        - Check fields exist and are non-empty (instead of checking exact values)
        - Check response message tags if required
        
        task_success semantics:
        - True  → resource created with required fields populated
        - False → resource missing or fields incomplete
        - None  → light validation not applicable (search tasks, etc.)
        """
        return TaskResult(
            task_success=None,  # None = N/A, not a failure
            task_id=self.get_task_id(),
            task_name=self.get_task_name(),
            execution_result=execution_result,
            assertion_error_message="Light validation not applicable for this task type",
        )

    
    def identify_failure_mode(self, task_result: TaskResult) -> TaskFailureMode:
        """
        Default implementation using metadata from YAML.
        Override if task-specific logic is needed.
        """
        if not self.required_tool_call_sets and not self.required_resource_types:
            return TaskFailureMode()  # Nothing to check against

        failure_mode = self.check_tool_calls(
            task_result,
            self.required_tool_call_sets,
            self.required_resource_types,
            self.prohibited_tools
        )

        # if failure_mode is None:
        #     failure_mode = TaskFailureMode(
        #         incorrect_tool_selection=False,
        #         incorrect_tool_order=False,
        #         incorrect_resource_type=False,
        #         error_codes=None
        #     )

        return failure_mode
    

    def poll_until_exists(self, resource_type, resource_id, timeout=5):
        """Polls until the resource exists on the FHIR server, or raises after timeout."""
        start = time.time()
        url = f"{self.FHIR_SERVER_URL}/{resource_type}/{resource_id}"
        logger.info(f"Polling for {resource_type}/{resource_id} to appear on the FHIR server (timeout={timeout}s)...")
        attempt = 0
        while time.time() - start < timeout:
            resp = requests.get(url, headers=self.HEADERS)
            attempt += 1
            if resp.status_code == 200:
                logger.info(f"Resource found: {resource_type}/{resource_id} (after {attempt} attempt(s), {time.time() - start:.2f}s)")
                return True
            else:
                logger.debug(f"Attempt {attempt}: {resource_type}/{resource_id} not found (status {resp.status_code}); retrying in 0.2s...")
            time.sleep(0.2)
        logger.warning(f"Timeout: {resource_type}/{resource_id} not found after {timeout}s and {attempt} attempt(s).")
        raise Exception(f"{resource_type}/{resource_id} not found after {timeout}s")


    def get_difficulty_level(self):
        # Return the difficulty level
        return self.difficulty_level