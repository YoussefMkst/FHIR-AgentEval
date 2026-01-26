import os
import sys
import csv
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import time

import yaml
import asyncio

# ──────────────────────────────────────────────────────────────────────────────
# Ensure project root is importable whether run as module (-m) or as a script
# ──────────────────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

# Local imports from the codebase
from agent.fhir_baseline import FHIRBaselineAgent  # type: ignore
#from agent.fhir_plan_execute_agent import FHIRPlanExecuteAgent
from agent.fhir_plan_execute_agent_v2 import FHIRPlanExecuteAgent # type: ignore
from agent.interfaces.core_agent_interface import AgentConfig  # type: ignore


# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
def build_logger() -> logging.Logger:
    """Create a module-level logger with level from LOG_LEVEL env (default INFO)."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return logging.getLogger("run-experiment-fhir-4configs")


# ──────────────────────────────────────────────────────────────────────────────
# Small helpers
# ──────────────────────────────────────────────────────────────────────────────
def _safe_attr(source: Any, key: str, default: Any = None) -> Any:
    """Safe getattr/get for both objects and dicts."""
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _bool(v: Any) -> bool:
    """Normalize truthy values to bool."""
    return True if v is True else False


def write_json(out_dir: Path, base_filename: str, payload: Dict[str, Any]) -> Path:
    """Write a JSON payload to <out_dir>/<base_filename>.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{base_filename}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


def _provenance(agent: Union[FHIRBaselineAgent, FHIRPlanExecuteAgent]) -> Dict[str, Any]:
    """Collect provenance fields for reproducibility (system prompt, endpoints, model id)."""
    try:
        cfg: AgentConfig = agent.config  # type: ignore[attr-defined]
    except Exception:
        return {
            "system_prompt_used": None,
            "active_endpoints": [],
            "model_id": None,
        }
    extra = getattr(cfg, "extra", {}) or {}
    additional = list(extra.get("additional_mcp_endpoints", []) or [])
    return {
        "system_prompt_used": getattr(cfg, "system_prompt", None),
        "active_endpoints": [getattr(cfg, "endpoint", None)] + additional if getattr(cfg, "endpoint", None) else additional,
        "model_id": getattr(cfg, "model_id", None),
    }


def _result_to_json_friendly(res: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make the agent's result JSON-safe and consistent:
      • execution_result / task_result / failure_mode are flattened to dicts
      • 'planner_steps' is INCLUDED ONLY IF present (not None)
    """
    # ---- execution_result (dataclass → dict)
    exec_res = res.get("execution_result")
    if exec_res and not isinstance(exec_res, dict):
        exec_res = {
            "execution_success": _safe_attr(exec_res, "execution_success", False),
            "response_msg": _safe_attr(exec_res, "response_msg", None),
            "token_total": _safe_attr(exec_res, "token_total", 0),
            "input_query": _safe_attr(exec_res, "input_query", None),
            "total_exec_ms": _safe_attr(exec_res, "total_exec_ms", None),
            "tool_order": _safe_attr(exec_res, "tool_order", []),
            "tool_exec_ms": _safe_attr(exec_res, "tool_exec_ms", {}),
            "tool_calls": _safe_attr(exec_res, "tool_calls", {}),
            "tool_call_counts": _safe_attr(exec_res, "tool_call_counts", {}),
        }

    # ---- task_result (object → dict)
    task_result = res.get("task_result")
    if task_result and not isinstance(task_result, dict):
        task_result = {
            "task_success": _safe_attr(task_result, "task_success", False),
            "assertion_error_message": _safe_attr(task_result, "assertion_error_message", None),
            "task_id": _safe_attr(task_result, "task_id", None),
            "task_name": _safe_attr(task_result, "task_name", None),
        }
    
    # ---- task_result_light (object → dict)
    task_result_light = res.get("task_result_light")
    if task_result_light and not isinstance(task_result_light, dict):
        task_result_light = {
            "task_success": _safe_attr(task_result_light, "task_success", None),
            "assertion_error_message": _safe_attr(task_result_light, "assertion_error_message", None),
            "task_id": _safe_attr(task_result_light, "task_id", None),
            "task_name": _safe_attr(task_result_light, "task_name", None),
        }

    # ---- failure_mode (object → dict)
    failure_mode = res.get("failure_mode")
    if failure_mode and not isinstance(failure_mode, dict):
        failure_mode = {
            "incorrect_tool_selection": _safe_attr(failure_mode, "incorrect_tool_selection", None),
            "incorrect_tool_order": _safe_attr(failure_mode, "incorrect_tool_order", None),
            "incorrect_resource_type": _safe_attr(failure_mode, "incorrect_resource_type", None),
            "prohibited_tool_used": _safe_attr(failure_mode, "prohibited_tool_used", None),
            "error_codes": _safe_attr(failure_mode, "error_codes", []),
        }

    shaped: Dict[str, Any] = {
        "task_module": res.get("task_module"),
        "task_class": res.get("task_class"),
        "execution_result": exec_res,
        "task_result": task_result,
        "task_result_light": task_result_light,
        "failure_mode": failure_mode,
        "final_text": res.get("final_text", ""),
    }

    # Include planner_steps ONLY if present and not None
    steps = res.get("planner_steps", None)
    if steps is not None:
        shaped["planner_steps"] = steps

        # Include planner_steps ONLY if present and not None
    planned_tools = res.get("planned_tools", None)
    if planned_tools is not None:
        shaped["planned_tools"] = planned_tools

    # Include raw_logs ONLY if present and not None
    raw_logs = res.get("raw_logs", None)
    if raw_logs is not None and isinstance(raw_logs, dict):
        shaped["raw_logs"] = raw_logs
    else:
        shaped["raw_logs"] = {"tools": [], "llms": []}

    # Include intermediate_steps ONLY if present and not None
    intermediate_steps = res.get("intermediate_steps", None)
    if intermediate_steps is not None:
        #shaped["intermediate_steps"] = intermediate_steps
        print("INTERMEDIATE STEPS: ", intermediate_steps)
                
    return shaped


# ──────────────────────────────────────────────────────────────────────────────
# Agent factories (5 baseline configs)
# ──────────────────────────────────────────────────────────────────────────────
async def _make_agents(
    fhir_sse_url: str,
    model_id: str,
    memory_endpoints: Optional[List[str]],
    planexec_planner_prompt_mem: Optional[str],  # unused now; kept for signature stability
    paraphrase: bool = False,  # whether to paraphrase task prompts
) -> Dict[str, Union[FHIRBaselineAgent, FHIRPlanExecuteAgent]]:
    """
    Build and initialize baseline agents:

      - baseline_nomemory                      : FHIR MCP only, no system prompt
      - baseline_with_references               : FHIR MCP + Specs MCP
      - baseline_with_memory_no_spec           : FHIR MCP + Memory MCP (trained without specs)
      - baseline_mem_spec_trained              : FHIR MCP + Memory MCP (trained with specs, no spec access)
      - baseline_with_memory_and_references    : FHIR MCP + Specs MCP + Memory MCP (trained with specs)
    """

    # Path to TextGrad-optimized prompt (same place the trainer writes)
    tg_prompt_path = ROOT_DIR / "prompts" / "trained" / "fhir_react_optimized_system.txt"
    tg_prompt_text = ""
    if tg_prompt_path.exists():
        tg_prompt_text = tg_prompt_path.read_text(encoding="utf-8")
    else:
        logging.getLogger("run-experiment-fhir-4configs").warning(
            "Optimized system prompt not found at %s; proceeding with empty prompt for baseline_textgrad.",
            tg_prompt_path,
        )
    
    print("TEXTGRAD PROMPT TEXT: ", tg_prompt_text)


    mem_prompt_path = ROOT_DIR / "prompts" / "fhir" / "fhir_baseline_system_prompt_with_mem.txt"
    mem_prompt_text = ""
    if mem_prompt_path.exists():
        mem_prompt_text = mem_prompt_path.read_text(encoding="utf-8")
    else:
        logging.getLogger("run-experiment-fhir-4configs").warning(
            "Memory system prompt not found at %s; proceeding with empty prompt for baseline_memory.",
            mem_prompt_path,
        )

    print("MEMORY PROMPT TEXT: ", mem_prompt_text)

    # Common instruction for all configs: retry search with different params before concluding "not found"
    SEARCH_RETRY_INSTRUCTION = """
    For search/retrieval tasks: if you get zero results, try alternative search parameters (e.g., different field names, reference formats, or without optional filters) before concluding the resource doesn't exist.
    """

    # Load FHIR specs reference prompt from file
    ref_prompt_path = ROOT_DIR / "prompts" / "fhir" / "fhir_baseline_system_prompt_with_refs.txt"
    SYSTEM_PROMPT_REF = ""
    if ref_prompt_path.exists():
        SYSTEM_PROMPT_REF = ref_prompt_path.read_text(encoding="utf-8")
    else:
        logging.getLogger("run-experiment-fhir-4configs").warning(
            "FHIR refs system prompt not found at %s; proceeding with empty prompt.",
            ref_prompt_path,
        )

    BASELINE_PROMPT = """You are a careful FHIR assistant. Think step-by-step. Use tools precisely and return concise final answers with required tags."""

    # 1) Baseline (FHIR only, NO system prompt, NO memory)
    baseline_cfg = AgentConfig(
        model_id=model_id,
        system_prompt=BASELINE_PROMPT +'\n\n'+ SEARCH_RETRY_INSTRUCTION,
        transport="mcp",
        endpoint=fhir_sse_url,
        extra={"additional_mcp_endpoints": []},
    )
    baseline_agent = FHIRBaselineAgent(baseline_cfg, paraphrase=paraphrase)

    # 2) Baseline + References (FHIR + Specs endpoints, NO memory)
    baseline_ref_cfg = AgentConfig(
        model_id=model_id,
        system_prompt=SYSTEM_PROMPT_REF + "\n\n" + SEARCH_RETRY_INSTRUCTION,
        transport="mcp",
        endpoint=fhir_sse_url,
        extra={"additional_mcp_endpoints": ["http://localhost:8010/fhir_specs"]},
    )
    baseline_ref_agent = FHIRBaselineAgent(baseline_ref_cfg, paraphrase=paraphrase)

    # 3) Baseline + Memory (trained WITHOUT spec server)
    # Uses memory from exp_fig_3_no_spec at http://localhost:8011/memory_fig_3_no_spec
    baseline_mem_no_spec_cfg = AgentConfig(
        model_id=model_id,
        system_prompt=mem_prompt_text + SEARCH_RETRY_INSTRUCTION,
        transport="mcp",
        endpoint=fhir_sse_url,
        extra={"additional_mcp_endpoints": ["http://localhost:8011/memory_fig_3_no_spec"]},
    )
    baseline_mem_no_spec_agent = FHIRBaselineAgent(baseline_mem_no_spec_cfg, paraphrase=paraphrase)

    # 4) Baseline + Memory (trained WITH spec server) + References
    # Uses memory from exp_fig_3_with_spec at http://localhost:8012/memory_fig_3_with_spec
    # ALSO has access to specs server
    baseline_mem_with_spec_cfg = AgentConfig(
        model_id=model_id,
        system_prompt=mem_prompt_text + "\n\n" + SYSTEM_PROMPT_REF + "\n\n" + SEARCH_RETRY_INSTRUCTION,
        transport="mcp",
        endpoint=fhir_sse_url,
        extra={"additional_mcp_endpoints": [
            "http://localhost:8012/memory_fig_3_with_spec",
            "http://localhost:8010/fhir_specs"
        ]},
    )
    baseline_mem_with_spec_agent = FHIRBaselineAgent(baseline_mem_with_spec_cfg, paraphrase=paraphrase)

    # 5) Baseline + Memory (trained WITH spec server) but NO spec server access
    # Uses memory from exp_fig_3_with_spec but doesn't have access to specs server
    baseline_mem_spec_trained_cfg = AgentConfig(
        model_id=model_id,
        system_prompt=mem_prompt_text + SEARCH_RETRY_INSTRUCTION,
        transport="mcp",
        endpoint=fhir_sse_url,
        extra={"additional_mcp_endpoints": ["http://localhost:8012/memory_fig_3_with_spec"]},
    )
    baseline_mem_spec_trained_agent = FHIRBaselineAgent(baseline_mem_spec_trained_cfg, paraphrase=paraphrase)

    # Initialize all configs concurrently
    await asyncio.gather(
        baseline_agent.ainit(),
        baseline_ref_agent.ainit(),
        baseline_mem_no_spec_agent.ainit(),
        baseline_mem_spec_trained_agent.ainit(),
        baseline_mem_with_spec_agent.ainit(),
    )

    return {
        "baseline_nomemory": baseline_agent,
        "baseline_with_references": baseline_ref_agent,
        "baseline_with_memory_no_spec": baseline_mem_no_spec_agent,
        "baseline_mem_spec_trained": baseline_mem_spec_trained_agent,
        "baseline_with_memory_and_references": baseline_mem_with_spec_agent,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Per-entry runner (uses agent.arun_task_entry only)
# ──────────────────────────────────────────────────────────────────────────────
async def _run_entry_with_agent(
    agent: Union[FHIRBaselineAgent, FHIRPlanExecuteAgent],
    entry: Dict[str, Any],
    variation_index: int,
    agent_tag: str,
    logger: logging.Logger,
) -> Dict[str, Any]:
    """
    Run exactly one task entry through the provided agent using its public interface.
    Return a JSON-serializable payload with the same fields you’ve been collecting.
    """
    # Validate required fields (mirrors your agents' checks)
    must = ["module", "class", "required_tool_call_sets", "required_resource_types", "prohibited_tools", "difficulty_level"]
    missing = [k for k in must if k not in entry]
    if missing:
        return {
            "task_module": entry.get("module"),
            "task_class": entry.get("class"),
            "variation": variation_index,
            "agent_tag": agent_tag,
            "error": f"Missing required task fields: {missing}",
        }

    try:
        res = await agent.arun_task_entry(entry)
        #sleep for 0.5 seconds
        await asyncio.sleep(2)
    except Exception as e:
        # Failure path: return a shaped error result without planner_steps
        logger.warning("Agent execution failed for %s.%s [%s]: %s", entry.get("module"), entry.get("class"), agent_tag, e)
        prov = _provenance(agent)
        return {
            "task_module": entry.get("module"),
            "task_class": entry.get("class"),
            "variation": variation_index,
            "agent_tag": agent_tag,
            "execution_result": {
                "execution_success": False,
                "response_msg": None,
                "token_total": 0,
                "input_query": entry.get("prompt") if "prompt" in entry else None,
                "total_exec_ms": None,
                "tool_order": [],
                "tool_exec_ms": {},
                "tool_calls": {},
                "tool_call_counts": {},
            },
            "task_result": {
                "task_success": False,
                "assertion_error_message": str(e),
                "task_id": None,
                "task_name": None,
            },
            "task_result_light": {
                "task_success": None,
                "assertion_error_message": "Light validation not run due to execution error",
                "task_id": None,
                "task_name": None,
            },
            "failure_mode": {},
            "final_text": "",
            "raw_logs": {"tools": [], "llms": []},  # placeholder for schema parity
            **prov,
        }

    # Success path: normalize result and add provenance/metadata
    shaped = _result_to_json_friendly(res)
    prov = _provenance(agent)
    shaped["variation"] = variation_index
    shaped["agent_tag"] = agent_tag

    return {**shaped, **prov}


# ──────────────────────────────────────────────────────────────────────────────
# Summary helpers
# ──────────────────────────────────────────────────────────────────────────────
def _summary_bump(summary: Dict[str, Dict[str, Dict[str, int]]], task_key: str, agent_tag: str, success: bool, light_success: Optional[bool] = None) -> None:
    """Accumulate per-task, per-agent success/total counts for both full and light validation."""
    if task_key not in summary:
        summary[task_key] = {}
    if agent_tag not in summary[task_key]:
        summary[task_key][agent_tag] = {"success": 0, "total": 0, "light_success": 0, "light_total": 0}
    summary[task_key][agent_tag]["total"] += 1
    if success:
        summary[task_key][agent_tag]["success"] += 1
    
    # Track light validation only if applicable (not None)
    if light_success is not None:
        summary[task_key][agent_tag]["light_total"] += 1
        if light_success:
            summary[task_key][agent_tag]["light_success"] += 1


def _write_summary_csv(out_dir: Path, summary: Dict[str, Dict[str, Dict[str, int]]]) -> Path:
    """Write a compact CSV with S/T (success/total) for each task × config, including light validation."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"experiment_summary_{ts}.csv"
    headers = [
        "Task",
        "Baseline_NoMem_S", "Baseline_NoMem_T", "Baseline_NoMem_Light_S", "Baseline_NoMem_Light_T",
        "Baseline_WithRefs_S", "Baseline_WithRefs_T", "Baseline_WithRefs_Light_S", "Baseline_WithRefs_Light_T",
        "Baseline_MemNoSpec_S", "Baseline_MemNoSpec_T", "Baseline_MemNoSpec_Light_S", "Baseline_MemNoSpec_Light_T",
        "Baseline_MemSpecTrained_S", "Baseline_MemSpecTrained_T", "Baseline_MemSpecTrained_Light_S", "Baseline_MemSpecTrained_Light_T",
        "Baseline_MemWithSpec_S", "Baseline_MemWithSpec_T", "Baseline_MemWithSpec_Light_S", "Baseline_MemWithSpec_Light_T",
    ]
    rows: List[List[str]] = []
    for task_key, per_agent in sorted(summary.items()):
        b0 = per_agent.get("baseline_nomemory", {"success": 0, "total": 0, "light_success": 0, "light_total": 0})
        br = per_agent.get("baseline_with_references", {"success": 0, "total": 0, "light_success": 0, "light_total": 0})
        bm_no = per_agent.get("baseline_with_memory_no_spec", {"success": 0, "total": 0, "light_success": 0, "light_total": 0})
        bm_spec_trained = per_agent.get("baseline_mem_spec_trained", {"success": 0, "total": 0, "light_success": 0, "light_total": 0})
        bm_with = per_agent.get("baseline_with_memory_and_references", {"success": 0, "total": 0, "light_success": 0, "light_total": 0})
        rows.append([
            task_key,
            str(b0["success"]), str(b0["total"]), str(b0["light_success"]), str(b0["light_total"]),
            str(br["success"]), str(br["total"]), str(br["light_success"]), str(br["light_total"]),
            str(bm_no["success"]), str(bm_no["total"]), str(bm_no["light_success"]), str(bm_no["light_total"]),
            str(bm_spec_trained["success"]), str(bm_spec_trained["total"]), str(bm_spec_trained["light_success"]), str(bm_spec_trained["light_total"]),
            str(bm_with["success"]), str(bm_with["total"]), str(bm_with["light_success"]), str(bm_with["light_total"]),
        ])
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return out_path


# ──────────────────────────────────────────────────────────────────────────────
# Main experiment
# ──────────────────────────────────────────────────────────────────────────────
async def run_experiment(
    variations_yaml: str,
    fhir_sse_url: str,
    model_id: str,
    out_dir: Path,
    logger: logging.Logger,
    memory_endpoints: Optional[List[str]] = None,
    planner_prompt_path: Optional[str] = None,
    paraphrase: bool = False,
) -> None:
    """
    For each variation in the YAML, run five agent configurations:
      baseline_nomemory, baseline_with_references, baseline_with_memory_no_spec,
      baseline_mem_spec_trained, baseline_with_memory_and_references.
    Write per-run JSON results to <out_dir>; print and write a CSV summary at the end.
    """
    # Load variations YAML
    ypath = Path(variations_yaml)
    with ypath.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    variations: List[Dict[str, Any]] = cfg.get("variations", [])

    # (Plan-exec prompt still loadable; unused now—kept to avoid wider changes)
    planexec_mem_planner_prompt: Optional[str] = None
    if planner_prompt_path:
        ppath = Path(planner_prompt_path)
        if not ppath.is_absolute():
            ppath = ROOT_DIR / ppath
        if ppath.exists():
            planexec_mem_planner_prompt = ppath.read_text(encoding="utf-8")
            logger.info("Loaded planner prompt from %s (unused in current 5-baseline run)", ppath)
        else:
            logger.warning("Planner prompt file not found at %s; ignoring.", ppath)

    # Build and initialize the agents
    agents = await _make_agents(
        fhir_sse_url=fhir_sse_url,
        model_id=model_id,
        memory_endpoints=memory_endpoints,
        planexec_planner_prompt_mem=planexec_mem_planner_prompt,
        paraphrase=paraphrase,
    )

    # Track per-(module,class) variation index (1..N)
    # Each unique (module, class) pair gets its own counter starting from 1
    variation_counter: Dict[Tuple[str, str], int] = {}

    # Summary structure for agent tags
    TAGS = [
        "baseline_nomemory",
        "baseline_with_references",
        "baseline_with_memory_no_spec",
        "baseline_mem_spec_trained",
        "baseline_with_memory_and_references",
    ]
    overall: Dict[str, Dict[str, int]] = {t: {"success": 0, "total": 0} for t in TAGS}
    summary: Dict[str, Dict[str, Dict[str, int]]] = {}

    # Iterate over variations and run each through all five agent configs
    for i, entry in enumerate(variations, start=1):
        task_module: str = entry.get("module", "")
        task_class: str = entry.get("class", "")
        key = (task_module, task_class)
        next_idx = variation_counter.get(key, 0) + 1
        variation_counter[key] = next_idx

        logger.info("[%d/%d] %s.%s (variation %d): running %d configs", i, len(variations), task_module, task_class, next_idx, len(TAGS))

        # Execute sequentially
        per_config_results: Dict[str, Dict[str, Any]] = {}
        for tag in TAGS:
            res = await _run_entry_with_agent(
                agent=agents[tag],  # type: ignore[index]
                entry=entry,
                variation_index=next_idx,
                agent_tag=tag,
                logger=logger,
            )
            per_config_results[tag] = res

        # Write JSON trace files with clear names (five configs)
        safe_task = f"{task_module}".replace("/", "_")
        out_paths = []
        name_map = {
            "baseline_nomemory": f"{safe_task}_v{next_idx}_baseline_no_mem",
            "baseline_with_references": f"{safe_task}_v{next_idx}_baseline_with_refs",
            "baseline_with_memory_no_spec": f"{safe_task}_v{next_idx}_baseline_mem_no_spec",
            "baseline_mem_spec_trained": f"{safe_task}_v{next_idx}_baseline_mem_spec_trained",
            "baseline_with_memory_and_references": f"{safe_task}_v{next_idx}_baseline_mem_with_spec_and_refs",
        }
        for tag, base_name in name_map.items():
            out_paths.append(write_json(out_dir, base_name, per_config_results[tag]))
        logger.info("Wrote traces → %s", " | ".join(map(str, out_paths)))

        # Update summary stats
        task_key = f"{task_module}.{task_class}"
        for tag in TAGS:
            success = _bool(_safe_attr(per_config_results[tag].get("task_result", {}), "task_success", False))
            light_result = per_config_results[tag].get("task_result_light", {})
            light_success = _safe_attr(light_result, "task_success", None)
            _summary_bump(summary, task_key, tag, success, light_success)
            overall[tag]["total"] += 1
            if success:
                overall[tag]["success"] += 1

    # ---- Print summary to terminal
    logger.info("=== SUMMARY: Success by task and config (Full/Light) ===")
    header = f"{'Task':50s}  {'NoMem F/L':14s}  {'WithRefs F/L':16s}  {'Mem-NoSpec F/L':18s}  {'Mem-SpecTrain F/L':20s}  {'Mem+Refs F/L':16s}"
    logger.info(header)
    logger.info("-" * len(header))
    for task_key, per_agent in sorted(summary.items()):
        b0 = per_agent.get("baseline_nomemory", {"success": 0, "total": 0, "light_success": 0, "light_total": 0})
        br = per_agent.get("baseline_with_references", {"success": 0, "total": 0, "light_success": 0, "light_total": 0})
        bm_no = per_agent.get("baseline_with_memory_no_spec", {"success": 0, "total": 0, "light_success": 0, "light_total": 0})
        bm_spec_trained = per_agent.get("baseline_mem_spec_trained", {"success": 0, "total": 0, "light_success": 0, "light_total": 0})
        bm_with = per_agent.get("baseline_with_memory_and_references", {"success": 0, "total": 0, "light_success": 0, "light_total": 0})
        
        # Format: Full(S/T)/Light(S/T)
        b0_str = f"{b0['success']}/{b0['total']} | {b0['light_success']}/{b0['light_total']}" if b0['light_total'] > 0 else f"{b0['success']}/{b0['total']} | N/A"
        br_str = f"{br['success']}/{br['total']} | {br['light_success']}/{br['light_total']}" if br['light_total'] > 0 else f"{br['success']}/{br['total']} | N/A"
        bm_no_str = f"{bm_no['success']}/{bm_no['total']} | {bm_no['light_success']}/{bm_no['light_total']}" if bm_no['light_total'] > 0 else f"{bm_no['success']}/{bm_no['total']} | N/A"
        bm_spec_str = f"{bm_spec_trained['success']}/{bm_spec_trained['total']} | {bm_spec_trained['light_success']}/{bm_spec_trained['light_total']}" if bm_spec_trained['light_total'] > 0 else f"{bm_spec_trained['success']}/{bm_spec_trained['total']} | N/A"
        bm_with_str = f"{bm_with['success']}/{bm_with['total']} | {bm_with['light_success']}/{bm_with['light_total']}" if bm_with['light_total'] > 0 else f"{bm_with['success']}/{bm_with['total']} | N/A"
        
        row = f"{task_key:50s}  {b0_str:14s}  {br_str:16s}  {bm_no_str:18s}  {bm_spec_str:20s}  {bm_with_str:16s}"
        logger.info(row)

    logger.info("-" * len(header))
    logger.info(
        "OVERALL → NoMem: %d/%d | WithRefs: %d/%d | Mem-NoSpec: %d/%d | Mem-SpecTrained: %d/%d | Mem+Refs: %d/%d",
        overall["baseline_nomemory"]["success"], overall["baseline_nomemory"]["total"],
        overall["baseline_with_references"]["success"], overall["baseline_with_references"]["total"],
        overall["baseline_with_memory_no_spec"]["success"], overall["baseline_with_memory_no_spec"]["total"],
        overall["baseline_mem_spec_trained"]["success"], overall["baseline_mem_spec_trained"]["total"],
        overall["baseline_with_memory_and_references"]["success"], overall["baseline_with_memory_and_references"]["total"],
    )

    # ---- Write CSV summary to the same target folder
    csv_path = _write_summary_csv(out_dir, summary)
    logger.info("Summary CSV written to: %s", csv_path)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run each FHIR variation with 5 baseline configs: no memory, with refs, memory (no spec training), memory (spec-trained, no spec access), memory+refs (with spec training+access). "
                    "Writes per-run JSON traces and a CSV summary at the end."
    )
    parser.add_argument(
        "--variations-yaml",
        default=str(ROOT_DIR / "environment" / "data" / "exp_1_task_variation_updated.yaml"),
        help="Path to variations YAML.",
    )
    parser.add_argument(
        "--fhir-sse-url",
        default=os.getenv("FHIR_MCP_SSE_URL", "http://localhost:8000/fhir_mcp"),
        help="Primary FHIR MCP SSE endpoint.",
    )
    parser.add_argument(
        "--memory-endpoints",
        nargs="*",
        #default=["http://localhost:8011/memory"],
        help="Additional MCP endpoints for memory tools (space-separated).",
    )
    parser.add_argument(
        "--planexec-planner-prompt-path",
        default=str(ROOT_DIR / "prompts" / "fhir" / "fhir_planner_system_prompt_with_mem.txt"),  # kept for compat
        help="(Unused in 5-baseline mode) Text file for planner SYSTEM prompt.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("BASELINE_MODEL", "openai:gpt-4.1-mini"),
        help="LLM model id (e.g., openai:gpt-4.1-mini).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for per-run JSON traces and the CSV summary",
    )
    parser.add_argument(
        "--paraphrase",
        action="store_true",
        default=False,
        help="Paraphrase task prompts before execution (default: False)",
    )

    args = parser.parse_args()
    logger = build_logger()

    ypath = Path(args.variations_yaml)
    if not ypath.is_absolute():
        ypath = ROOT_DIR / ypath

    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT_DIR / out_dir

    logger.info(
        "Starting 5-config experiment | yaml=%s | endpoint=%s | model=%s | out=%s",
        ypath, args.fhir_sse_url, args.model, out_dir
    )

    asyncio.run(
        run_experiment(
            variations_yaml=str(ypath),
            fhir_sse_url=args.fhir_sse_url,
            model_id=args.model,
            out_dir=out_dir,
            logger=logger,
            memory_endpoints=args.memory_endpoints,
            planner_prompt_path=args.planexec_planner_prompt_path,
            paraphrase=args.paraphrase,
        )
    )


if __name__ == "__main__":
    main()
