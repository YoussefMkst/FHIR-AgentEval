# reflexion_workflow.py — Reflexion loop over YAML tasks (Actor=Local ReAct Agent, Evaluator LLM, Self-Reflection LLM)


import os, json, time, uuid, argparse, logging, yaml, asyncio
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import asdict
from dotenv import load_dotenv
from pathlib import Path
import sys

# Ensure repo root is on sys.path when running this file directly
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from langchain_openai import ChatOpenAI
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from utils.callbacks import ToolCallRecorder, LLMUsageRecorder, aggregate_trace
from utils.task_loader import build_task
from utils.prompt_paraphraser import paraphrase_prompt
from utils.runtime_clock import _build_clock_block
from langchain.tools import StructuredTool
from langchain_core.tools import BaseTool
from tasks.fhir_tasks_modular.task_interface_modular import ExecutionResult
from environment.mcp.memory_servers.memory_stores.fhir_reflexion_memory_store import init_store, add_entry, add_macro, add_micro

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reflexion")

# --------------------------------------------------------------------
# ENV
FHIR_MCP_SSE_URL = os.getenv("FHIR_MCP_SSE_URL", "http://localhost:8000/fhir_mcp")
FHIR_SPECS_MCP_SSE_URL = os.getenv("FHIR_SPECS_MCP_SSE_URL", "http://localhost:8010/fhir_specs")
FHIR_SERVER_URL   = os.getenv("FHIR_SERVER_URL", "http://localhost:7070/fhir")

EVAL_MODEL         = os.getenv("EVALUATOR_MODEL",  "gpt-4.1")
REFLECT_MODEL      = os.getenv("REFLECTOR_MODEL",  "o4-mini")
AGENT_MODEL        = os.getenv("AGENT_MODEL",      "openai:gpt-4.1")

ROOT_DIR     = Path(__file__).resolve().parents[1]
DATA_DIR     = Path(__file__).resolve().parents[1] / "environment" / "data"
INDEXES_DIR  = Path(__file__).resolve().parents[1] / "environment" / "indexes"
TASKS_DIR    = Path(__file__).resolve().parents[1] / "tasks" / "fhir_tasks"

LTM_DIR            = os.getenv("LTM_DIR", str(INDEXES_DIR / "reflexion_faiss" / "exp_fig_no_spec_test"))
MAX_TRIALS_DEFAULT = int(os.getenv("MAX_TRIALS", "2"))

# Reflection quality over token usage → generous but safe budgets
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "30"))                # how many raw tool calls to pass to judges
MAX_JSON_CHARS_PER_CALL = int(os.getenv("MAX_JSON_CHARS_PER_CALL", "12000"))  # cap per tool output for judges
MAX_OO_CHARS = int(os.getenv("MAX_OO_CHARS", "6000"))                  # if OO ≤ this, agent sees it verbatim

if not FHIR_SERVER_URL:
    raise RuntimeError("Missing FHIR_SERVER_URL in .env")

# Init local LTM store (FAISS)
try:
    Path(LTM_DIR).mkdir(parents=True, exist_ok=True)
except Exception:
    pass
init_store(LTM_DIR)

# Reading system prompts
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts" / "reflexion_prompts"

def _load_prompt(filename: str) -> str:
    """Load a prompt from the reflexion_prompts directory."""
    filepath = PROMPTS_DIR / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

EVALUATOR_SYSTEM = _load_prompt("evaluator_system.txt")
REFLECTOR_SYSTEM = _load_prompt("reflector_system.txt")
REFLECTOR_SPEC_SYSTEM = _load_prompt("reflector_spec_system.txt")


# --------------------------------------------------------------------
# MCP tools and agent setup
# --------------------------------------------------------------------
async def load_fhir_tools(url: str):
    """Load FHIR tools from MCP server over SSE."""
    client = MultiServerMCPClient({"fhir": {"transport": "sse", "url": url}})
    tools = await client.get_tools()
    if not tools:
        log.warning("No tools discovered from FHIR MCP at %s", url)
    else:
        log.info("Loaded %d MCP tools from %s", len(tools), url)
    return tools


async def load_fhir_specs_tools(url: str):
    """Load FHIR **specs** tools (not live CRUD) from MCP server over SSE."""
    client = MultiServerMCPClient({"fhir_specs": {"transport": "sse", "url": url}})
    tools = await client.get_tools()
    if not tools:
        log.warning("No tools discovered from FHIR SPECS MCP at %s", url)
    else:
        log.info("Loaded %d FHIR SPECS tools from %s", len(tools), url)
    return tools

def _cap(text: str, n: int = 800) -> str:
    try:
        return text if len(text) <= n else (text[:n] + "…")
    except Exception:
        return str(text)[:n] + "…"

def _safe_dump(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)

def _string_cap(s: str, max_chars: int) -> Dict[str, Any]:
    """Always-JSON-valid cap wrapper."""
    return {"_truncated": True, "head": s[:max_chars]}

def budgeted_json(obj: Any, max_chars=12000, max_list=50, max_str=2000) -> Any:
    """
    Trim lists/strings to keep JSON size bounded while preserving structure.
    If still too big, fall back to a capped string wrapper.
    """
    def trim(o):
        if isinstance(o, dict):
            return {k: trim(v) for k, v in o.items()}
        if isinstance(o, list):
            # keep head of arrays (typical culprit: Bundle.entry)
            if len(o) > max_list:
                o = o[:max_list]
            return [trim(v) for v in o]
        if isinstance(o, str):
            return o if len(o) <= max_str else (o[:max_str] + "…")
        return o

    candidate = trim(obj)
    s = _safe_dump(candidate)
    if len(s) <= max_chars:
        return candidate
    return _string_cap(s, max_chars)

def _redact_operation_outcome(oo: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Preserve entire 'issue' array (the recovery signal) and minimal helpful headers.
    """
    out: Dict[str, Any] = {"resourceType": "OperationOutcome", "issue": oo.get("issue", [])}
    if isinstance(oo.get("id"), str):
        out["id"] = oo["id"]
    if extra:
        for k in ("status", "method", "url"):
            if extra.get(k) is not None:
                out[k] = extra[k]
    return out

def _summarize_fhir_output(tool_name: str, args: Dict[str, Any], out: Any) -> str:
    """
    What the AGENT will see as a tool return:
    - Bundle: summarized (entries count + first few refs)
    - OperationOutcome: full if small, otherwise issues-only
    - MCP error envelope (non-2xx): compact JSON with status/error/etc.; if it includes an OO, apply OO rules
    - Single resource: ResourceType/id
    - Fallback: top-level keys
    """
    def j(d): 
        try: return json.dumps(d, ensure_ascii=False)
        except Exception: return str(d)

    try:
        if isinstance(out, dict):
            # MCP error envelope from server
            if "error" in out and "status" in out:
                # If the server included an OperationOutcome, let the agent see it (as below)
                if isinstance(out.get("operationOutcome"), dict) and out["operationOutcome"].get("resourceType") == "OperationOutcome":
                    oo = out["operationOutcome"]
                    s = _safe_dump(oo)
                    if len(s) <= MAX_OO_CHARS:
                        return s
                    return j(_redact_operation_outcome(oo, extra={"status": out.get("status"),
                                                                 "method": out.get("method"),
                                                                 "url": out.get("url")}))
                # Otherwise compact error for agent
                return j({
                    "__mcp_error__": True,
                    "tool": tool_name,
                    "status": out.get("status"),
                    "error": out.get("error"),
                    "issue_codes": out.get("issue_codes"),
                    "first_expression": out.get("first_expression"),
                    "diagnostics": (out.get("diagnostics") or out.get("body_excerpt") or "")[:1000],
                })

            rt = out.get("resourceType")

            # OperationOutcome (even if 2xx body)
            if rt == "OperationOutcome":
                s = _safe_dump(out)
                if len(s) <= MAX_OO_CHARS:
                    return s  # full OO → best for agent recovery
                return j(_redact_operation_outcome(out))

            # Bundle summary (keep planning crisp)
            if rt == "Bundle" or ("entry" in out and isinstance(out.get("entry"), list)):
                entries = out.get("entry") or []
                first = []
                for e in entries[:3]:
                    res = (e or {}).get("resource") or {}
                    if res.get("resourceType") and res.get("id"):
                        first.append(f"{res['resourceType']}/{res['id']}")
                return j({"__bundle__": True, "tool": tool_name, "entries": len(entries), "first": first})

            # Single resource success → short ref
            if rt and out.get("id"):
                return j({"__resource__": True, "tool": tool_name, "ref": f"{rt}/{out['id']}"})

            # Fallback: keys only
            return j({"__keys__": True, "tool": tool_name, "keys": sorted(list(out.keys()))[:10]})

        # Non-dict fallback
        return _cap(f"{tool_name}: {str(out)}")
    except Exception as e:
        return json.dumps({"__summary_error__": True, "tool": tool_name, "err": type(e).__name__})

def _wrap_tool_with_summary(t, recorder: Optional[ToolCallRecorder] = None) -> BaseTool:
    """
    Wrap a tool so:
      - we RECORD the RAW payload for judges (Evaluator/Reflector),
      - the AGENT gets a compact, LLM-friendly summary.
    """
    name = getattr(t, "name", "tool")
    desc = getattr(t, "description", "")
    args_schema = getattr(t, "args_schema", None)

    # Ensure recorder has a raw bucket even if the class doesn't define it
    if recorder is not None and not hasattr(recorder, "raw_records"):
        setattr(recorder, "raw_records", [])

    def _record_raw(tool_name: str, kwargs: Dict[str, Any], raw: Any):
        if recorder is None:
            return
        try:
            recorder.raw_records.append({"tool": tool_name, "input": kwargs, "output": raw})
        except Exception:
            pass

    async def _coro(**kwargs):
        try:
            # Prefer async invoke if available
            if hasattr(t, "ainvoke"):
                raw = await t.ainvoke(kwargs)
            else:
                raw = t.invoke(kwargs)
        except Exception as e:
            _record_raw(name, kwargs, {"exception": f"{type(e).__name__}: {e}"})
            return _cap(f"{name}: ERROR {type(e).__name__}: {e}")

        # Record RAW before summarizing
        _record_raw(name, kwargs, raw)
        # Return compact to agent
        return _summarize_fhir_output(name, kwargs, raw)

    try:
        args_schema = getattr(t, "args_schema", None)
        if args_schema is None:
            # No schema → skip wrapping to avoid breaking invocation
            return t

        def _sync_func(**kwargs):
            return t.invoke(kwargs)

        wrapped = StructuredTool.from_function(
            name=name,
            description=desc,
            args_schema=args_schema,
            #func=_sync_func,
            coroutine=_coro,
        )

        return wrapped
    except Exception:
        return t

def wrap_tools_with_summaries(tools: List[Any], recorder: Optional[ToolCallRecorder] = None) -> List[Any]:
    return [_wrap_tool_with_summary(t, recorder=recorder) for t in tools]

def build_agent(tools, model_id: str):
    """Build a ReAct agent with the given tools and model."""
    llm = init_chat_model(model_id)
    return create_react_agent(llm, tools)

def extract_text_from_result(result: Any) -> str:
    """Extract final text from agent result."""
    try:
        if isinstance(result, dict) and "messages" in result:
            msgs = result["messages"]
            if isinstance(msgs, list) and msgs:
                last = msgs[-1]
                content = getattr(last, "content", None)
                if isinstance(content, str):
                    return content
        if hasattr(result, "content"):
            return result.content
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False)
    except Exception:
        return str(result)


def extract_agent_output(result: Any) -> str:
    if isinstance(result, dict):
        direct = result.get("output")
        if isinstance(direct, str) and direct:
            return direct
    return extract_text_from_result(result)

# --------------------------------------------------------------------
# Local agent execution (replaces n8n)
# --------------------------------------------------------------------
async def call_local_agent(prompt: str, tools) -> Tuple[str, str, Dict[str, Any]]:
    """
    Execute a local ReAct agent with the given prompt and tools.
    Returns (final_message, execution_id, trace_dict).
    """
    # Recorder first, so wrappers can stash RAW
    tool_rec = ToolCallRecorder()
    llm_rec = LLMUsageRecorder()
    safe_tools = wrap_tools_with_summaries(tools, recorder=tool_rec)

    agent = build_agent(safe_tools, AGENT_MODEL)
    started_at = time.perf_counter()

    # Build runtime clock context
    clock = _build_clock_block()

    # Run the agent with system + human prompt (clock prepended to provide time context)
    try:
        result = await agent.ainvoke(
            {"messages": [("system", "You are a FHIR ReAct agent. Think step-by-step and use tools as needed. For search/retrieval tasks: if you get zero results, try alternative search parameters (e.g., different field names, reference formats, or without optional filters) before concluding the resource doesn't exist."),
                          ("human", f"{prompt}\n\n{clock}")]},
            config={"callbacks": [tool_rec, llm_rec]}
        )
    except Exception as e:
        log.warning(f"Agent execution failed: {type(e).__name__}: {e}")
        log.warning("Continuing to next task...")
        return f"Task failed: {type(e).__name__}", str(uuid.uuid4()), {
            "tool_order": [],
            "tool_calls": {},
            "error": str(e)
        }

    final_text = extract_text_from_result(result)
    exec_id = str(uuid.uuid4())
    tr = aggregate_trace(tool_rec, llm_rec, started_at)

    # Normalize tool_calls to the expected shape: dict[name] -> list[{input: dict, output: str}]
    grouped = tr.get("tool_calls_grouped", {}) or {}
    norm_calls: Dict[str, List[Dict[str, Any]]] = {}
    for name, records in grouped.items():
        lst: List[Dict[str, Any]] = []
        for rec in records or []:
            raw_in = rec.get("input", "")
            parsed_in: Any = {}
            if isinstance(raw_in, dict):
                parsed_in = raw_in
            elif isinstance(raw_in, str) and raw_in:
                try:
                    parsed_in = json.loads(raw_in)
                except Exception:
                    maybe = _safe_json_loads(raw_in)
                    parsed_in = maybe if isinstance(maybe, dict) else {}
            out_val = rec.get("output")
            if not isinstance(out_val, str):
                try:
                    out_val = json.dumps(out_val, ensure_ascii=False)
                except Exception:
                    out_val = str(out_val)
            lst.append({"input": parsed_in, "output": out_val})
        norm_calls[name] = lst

    # Judges get RAW (pruned to stay within sensible bounds)
    tools_raw = getattr(tool_rec, "raw_records", []) or []
    raw_logs = {
        "tools_raw": tools_raw,
        "tools_slim": getattr(tool_rec, "records", []),  # whatever your callback already aggregates
        "llms":  getattr(llm_rec, "calls", []),
    }

    trace_dict = {
        "tool_order": tr.get("tool_order", []),
        "tool_calls": norm_calls,
        "tool_exec_ms": tr.get("tool_exec_ms", {}),
        "tool_call_counts": tr.get("tool_call_counts", {}),
        "token_total": (tr.get("token_breakdown") or {}).get("total_tokens"),
        "total_exec_ms": tr.get("total_exec_ms"),
        "workflow_name": "local_react_agent",
        "input_query": prompt,
        "raw_logs": raw_logs
    }

    return final_text, exec_id, trace_dict

# --------------------------------------------------------------------
# LLMs (system prompts updated to explain inputs & constraints)
def make_evaluator_llm() -> ChatOpenAI:
    # Advisory evaluator (does NOT decide pass/fail; your task.validate_response() does)
    return ChatOpenAI(model=EVAL_MODEL, temperature=0)


async def make_reflector_tools_agent(model_id: str, specs_url: Optional[str] = None, use_specs: bool = False) -> Optional[AgentExecutor]:
    if specs_url is None:
        tools = []
    else:
        try:
            tools = await load_fhir_specs_tools(specs_url)
            tools = [_wrap_safe(t) for t in tools]
        except Exception as e:
            log.warning("Failed to load FHIR SPECS tools from %s: %s", specs_url, e)
            return None

        if not tools:
            return None

    try:
        normalized_model = model_id.split(":", 1)[1] if model_id and ":" in model_id else model_id
        llm = ChatOpenAI(model=normalized_model)
        
        # Conditionally append spec system prompt based on use_specs flag
        system_prompt = REFLECTOR_SYSTEM
        if use_specs:
            system_prompt = REFLECTOR_SYSTEM + "\n\n" + REFLECTOR_SPEC_SYSTEM
            log.info("Using FHIR specs-assisted reflector prompt")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        agent = create_openai_tools_agent(llm=llm, tools=tools, prompt=prompt)
        log.info("Initialized reflector tools agent with %d FHIR SPECS tools", len(tools))
        return AgentExecutor(agent=agent, tools=tools, verbose=False)
    except Exception as e:
        log.warning("Failed to initialize reflector tools agent: %s: %s", type(e).__name__, e)
        return None


# --------------------------------------------------------------------
# Helpers
def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        # Try to salvage by grabbing the largest {...} block
        try:
            start = text.find("{")
            end   = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end+1])
        except Exception:
            return None
    return None


def summarize_tool_calls(tool_calls: Optional[Dict[str, List[Dict[str, Any]]]], limit_per_tool: int = 2) -> Dict[str, Any]:
    """
    Keep this lightweight to avoid huge prompts.
    For each tool, keep up to limit_per_tool recent calls with input.resourceType and status-ish output.
    (This is NOT what we send to judges; judges get pruned RAW via prune_raw().)
    """
    if not tool_calls:
        return {}
    slim: Dict[str, Any] = {}
    for tool, calls in tool_calls.items():
        subset = calls[-limit_per_tool:]
        proj = []
        for c in subset:
            inp = c.get("input") or {}
            out = c.get("output")
            proj.append({
                "resourceType": (inp.get("resourceType") if isinstance(inp, dict) else None),
                "status": str(out)[:240] if isinstance(out, str) else ("json" if out else None)
            })
        slim[tool] = proj
    return slim

def prune_raw(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Prefer RAW for judges; only truncate pathological payloads.
    Never cut OperationOutcome entirely; if too big, keep at least full 'issue' array.
    """
    out = []
    for c in (calls or [])[:MAX_TOOL_CALLS]:
        outp = c.get("output")
        # Preserve OperationOutcome
        if isinstance(outp, dict) and outp.get("resourceType") == "OperationOutcome":
            s = _safe_dump(outp)
            if len(s) <= MAX_JSON_CHARS_PER_CALL:
                out.append({"tool": c.get("tool"), "input": c.get("input"), "output": outp})
                continue
            issues_only = {"resourceType": "OperationOutcome", "issue": outp.get("issue", [])}
            out.append({"tool": c.get("tool"), "input": c.get("input"), "output": issues_only})
            continue

        # Keep raw unless huge
        s = _safe_dump(outp)
        if len(s) <= MAX_JSON_CHARS_PER_CALL:
            out.append({"tool": c.get("tool"), "input": c.get("input"), "output": outp})
        else:
            out.append({"tool": c.get("tool"), "input": c.get("input"), "output": budgeted_json(outp, MAX_JSON_CHARS_PER_CALL)})
    return out


    # error hardening for tools
def _wrap_safe(tool: BaseTool) -> BaseTool:
    # If the tool raises ToolException, return this text to the LLM instead
    tool.handle_tool_error = lambda e: f"TOOL_ERROR: {type(e).__name__}: {e}"
    # If input validation fails, also return a message instead of raising
    tool.handle_validation_error = lambda e: f"VALIDATION_ERROR: {e}"
    return tool
# --------------------------------------------------------------------
# Core Reflexion loop for one task
async def run_task(task_entry: Dict[str, Any], max_trials: int, use_specs: bool = False) -> Dict[str, Any]:
    task = build_task(task_entry)

    # Prepare environment for this task
    log.info("Cleaning & preparing test data for %s.%s", task_entry["module"], task_entry["class"])
    task.cleanup_test_data()
    task.prepare_test_data()
    original_prompt = task.get_prompt()
    
    # Paraphrase the prompt to simulate real-world variations
    log.info("Paraphrasing task prompt for realistic variation")
    prompt = paraphrase_prompt(original_prompt)
    log.info("Paraphrased prompt: %s", prompt)

    #prompt = original_prompt
    # log.info("Prompt not paraphrased: %s", prompt)
    # Load FHIR tools from MCP server
    tools = await load_fhir_tools(FHIR_MCP_SSE_URL)

    # error hardening for tools
    tools = [_wrap_safe(t) for t in tools]

    evaluator = make_evaluator_llm()
    specs_url = FHIR_SPECS_MCP_SSE_URL if use_specs else None
    reflector_agent = await make_reflector_tools_agent(REFLECT_MODEL, specs_url=specs_url, use_specs=use_specs)


    # Expose constraints once (Evaluator/Reflector rely on these)
    constraints = {
        "required_tool_call_sets": task_entry.get("required_tool_call_sets", []),
        "required_resource_types": task_entry.get("required_resource_types", []),
        "prohibited_tools": task_entry.get("prohibited_tools", []),
    }

    print("CONSTRAINTS: ", constraints)

    results: List[Dict[str, Any]] = []
    for t in range(max_trials):
        log.info("Trial %d/%d → Actor (Local ReAct Agent)", t+1, max_trials)

        # 1) ACTOR
        final_msg, exec_id, exec_log = await call_local_agent(prompt, tools)

        # 2) TRAJECTORY (execution log)
        tool_order = exec_log.get("tool_order", [])
        tool_calls = exec_log.get("tool_calls", {})
        tool_calls_slim = summarize_tool_calls(tool_calls)

        # 3) DETERMINISTIC EVALUATION
        det_exec = ExecutionResult(
            execution_success=True,
            response_msg=final_msg,
            token_total=exec_log.get("token_total"),
            input_query=exec_log.get("input_query"),
            total_exec_ms=exec_log.get("total_exec_ms"),
            tool_order=tool_order,
            tool_exec_ms=exec_log.get("tool_exec_ms"),
            tool_calls=tool_calls,
            tool_call_counts=exec_log.get("tool_call_counts"),
        )
        validator = task.validate_response
        det_result = validator(det_exec)
        success = bool(det_result.task_success)
        assertions = det_result.assertion_error_message or ""
        log.info("Deterministic result: success=%s ; assertions=%s", success, assertions or "<none>")

        # 3b) Failure diagnostics for Reflexion (order/selection/resource/prohibited)
        failure_mode_obj = task.identify_failure_mode(det_result)  # may be None
        failure_mode = asdict(failure_mode_obj) if failure_mode_obj else None

        # 3c) RAW logs (for judges), pruned to keep messages valid and helpful
        raw_logs = exec_log.get("raw_logs", {})
        tools_raw_pruned = prune_raw(raw_logs.get("tools_raw", []))

        # 4) LLM EVALUATOR (advisory JSON)
        eval_input = {
            "task_prompt": prompt,
            "deterministic_result": {"success": success, "assertions": assertions},
            "trajectory": {"tool_order": tool_order, "tool_calls": tools_raw_pruned},
            "constraints": constraints,
            "failure_mode": failure_mode,
        }
        eval_msg = [
            {"role": "system", "content": EVALUATOR_SYSTEM},
            {"role": "user",   "content": json.dumps(eval_input, ensure_ascii=False)}
        ]
        eval_raw = evaluator.invoke(eval_msg).content
        eval_json = _safe_json_loads(eval_raw) or {
            "score": 1.0 if success else 0.0,
            "critique": eval_raw[:400],
            "failure_tags": [],
            "advice": ""
        }

        # 5) SELF-REFLECTION
        reflect_input = {
            "task_prompt": prompt,
            "success": success,
            "assertions": assertions,
            "trajectory": {"tool_order": tool_order, "tool_calls": tools_raw_pruned},
            "constraints": constraints,
            "failure_mode": failure_mode,
            "evaluator": eval_json
        }
        reflect_payload = json.dumps(reflect_input, ensure_ascii=False)
        ref_raw = ""

        if reflector_agent is not None:
            try:
                agent_result = await reflector_agent.ainvoke({
                    "input": reflect_payload,
                    "chat_history": []
                })
                ref_raw = extract_agent_output(agent_result)
            except Exception as e:
                log.warning("Reflector tools agent failure: %s: %s", type(e).__name__, e)
                reflector_agent = None

        if not ref_raw:
            raise RuntimeError("Reflector tools agent did not return output")
        ref_json = _safe_json_loads(ref_raw) or {
            "reflection_text": ref_raw[:800],
            "micro": [],
            "macro_summary": "",
            "heuristic": ""
        }

        # 6) STORE to LTM
        stored_any = False
        try:
            try:
                add_macro(
                    text=ref_json.get("reflection_text", ""),
                    macro_summary=ref_json.get("macro_summary", ""),
                    heuristic=ref_json.get("heuristic", ""),
                    tags=[task.get_task_name()],
                    success=success,
                    extras={"task_id": task.get_task_id()}
                )
                stored_any = True
            except Exception:
                pass

            for tip in ref_json.get("micro", []) or []:
                try:
                    add_micro(
                        resource=tip.get("resource") or "",
                        operation=tip.get("operation") or "",
                        tip=tip.get("tip") or "",
                        success=success,
                        extras={"task_id": task.get_task_id()}
                    )
                    stored_any = True
                except Exception:
                    pass
        except Exception:
            pass

        if not stored_any:
            add_entry({
                "type":       "macro" if success else "micro",
                "text":       ref_json.get("reflection_text") or ref_json.get("macro_summary") or "",
                "micro":      ref_json.get("micro", []),
                "macro":      ref_json.get("macro_summary", ""),
                "heuristic":  ref_json.get("heuristic", ""),
                "task_id":    getattr(task, "get_task_id", lambda: None)(),
                "success":    success,
                "created_at": time.time(),
                "resource_types": task_entry.get("required_resource_types", []),
            })

        # 7) persist result for this trial
        trial_res = {
            "trial": t+1,
            "execution_id": exec_id,
            "success": success,
            "assertions": assertions,
            "evaluator": eval_json,
            "reflection": ref_json,
            "tool_order": tool_order,
            "failure_mode": failure_mode
        }
        results.append(trial_res)

        # Stop if passed
        if success:
            log.info("Task PASSED on trial %d", t+1)
            break
        else:
            log.info("Task FAILED on trial %d; will retry if trials remain", t+1)

    return {
        "task_module": task_entry["module"],
        "task_class":  task_entry["class"],
        "results": results,
        "passed": any(r["success"] for r in results)
    }

# --------------------------------------------------------------------
# Run all tasks from YAML
async def run_from_yaml(yaml_path: str, max_trials: int, use_specs: bool = False):
    # Resolve YAML path relative to @data/ if not absolute
    ypath = Path(yaml_path)
    if not ypath.is_absolute():
        ypath = DATA_DIR / ypath
    with open(ypath, "r") as f:
        cfg = yaml.safe_load(f)

    # Accept both "variations" (modular) and "tasks" (legacy) keys
    tasks: List[Dict[str, Any]] = cfg.get("variations") or cfg.get("tasks", [])
    if not tasks:
        raise ValueError("No tasks or variations found in YAML.")

    summary = []
    for entry in tasks:
        log.info("=== Running task %s.%s ===", entry["module"], entry["class"])
        summary.append(await run_task(entry, max_trials, use_specs=use_specs))

    print(json.dumps({"summary": summary}, indent=2, ensure_ascii=False))

# --------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Reflexion loop over YAML-defined tasks")
    ap.add_argument("--yaml", default="new_tasks_21a_21c_2_variations.yaml", help="Path to YAML file (relative to environment/data/ if not absolute)")
    ap.add_argument("--max-trials", type=int, default=MAX_TRIALS_DEFAULT, help="Max trials per task")
    ap.add_argument("--use-specs", action="store_true", default=False, help="Enable FHIR specs-assisted reflector prompt (appends REFLECTOR_SPEC_SYSTEM to REFLECTOR_SYSTEM)")
    args = ap.parse_args()

    # If relative path, resolve under environment/data by default
    ypath = args.yaml
    if not Path(ypath).is_absolute():
        ypath = str(DATA_DIR / ypath)

    asyncio.run(run_from_yaml(ypath, args.max_trials, use_specs=args.use_specs))
 