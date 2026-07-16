"""
Shared per-variation harness for the FHIR experiment runners.

Both `experiments/run_experiment_fhir.py` (LangChain baselines) and
`experiments/run_experiment_fhir_claude_code.py` (Claude Code driver) build
their five agents differently, but the surrounding loop — JSON normalization,
per-tag JSON output, summary tracking, terminal print, CSV write — is
identical. That logic lives here so both runners are kept small and focused on
their driver-specific concerns.

Public API:
- DEFAULT_TAGS / DEFAULT_NAME_MAP_SUFFIXES: the canonical 5-tag scheme
- build_logger(): module logger
- write_json(): per-run trace writer
- run_variations(): the per-variation harness used by both runners
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# Canonical tag scheme. Both LangChain and Claude Code runners use the same
# five tags so downstream JSON filenames, CSV columns, and analysis notebooks
# are interchangeable across drivers.
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_TAGS: List[str] = [
    "baseline_nomemory",
    "baseline_with_references",
    "baseline_with_memory_no_spec",
    "baseline_mem_spec_trained",
    "baseline_with_memory_and_references",
]

DEFAULT_NAME_MAP_SUFFIXES: Dict[str, str] = {
    "baseline_nomemory": "baseline_no_mem",
    "baseline_with_references": "baseline_with_refs",
    "baseline_with_memory_no_spec": "baseline_mem_no_spec",
    "baseline_mem_spec_trained": "baseline_mem_spec_trained",
    "baseline_with_memory_and_references": "baseline_mem_with_spec_and_refs",
}


# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
def build_logger(name: str = "run-experiment-fhir") -> logging.Logger:
    """Module-level logger; level from LOG_LEVEL env (default INFO)."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return logging.getLogger(name)


# ──────────────────────────────────────────────────────────────────────────────
# Small helpers
# ──────────────────────────────────────────────────────────────────────────────
def _safe_attr(source: Any, key: str, default: Any = None) -> Any:
    """getattr/get against either an object or a dict."""
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _bool(v: Any) -> bool:
    return True if v is True else False


def write_json(out_dir: Path, base_filename: str, payload: Dict[str, Any]) -> Path:
    """Write a JSON payload to <out_dir>/<base_filename>.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{base_filename}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


def _provenance(agent: Any) -> Dict[str, Any]:
    """Provenance fields (system prompt, endpoints, model id) for reproducibility."""
    try:
        cfg = agent.config
    except Exception:
        return {"system_prompt_used": None, "active_endpoints": [], "model_id": None}
    extra = getattr(cfg, "extra", {}) or {}
    additional = list(extra.get("additional_mcp_endpoints", []) or [])
    endpoint = getattr(cfg, "endpoint", None)
    return {
        "system_prompt_used": getattr(cfg, "system_prompt", None),
        "active_endpoints": [endpoint] + additional if endpoint else additional,
        "model_id": getattr(cfg, "model_id", None),
    }


def _result_to_json_friendly(res: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten dataclass-typed agent results into JSON-safe dicts. Includes
    optional planner_steps / planned_tools / raw_logs only when present."""
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

    task_result = res.get("task_result")
    if task_result and not isinstance(task_result, dict):
        task_result = {
            "task_success": _safe_attr(task_result, "task_success", False),
            "assertion_error_message": _safe_attr(task_result, "assertion_error_message", None),
            "task_id": _safe_attr(task_result, "task_id", None),
            "task_name": _safe_attr(task_result, "task_name", None),
        }

    task_result_light = res.get("task_result_light")
    if task_result_light and not isinstance(task_result_light, dict):
        task_result_light = {
            "task_success": _safe_attr(task_result_light, "task_success", None),
            "assertion_error_message": _safe_attr(task_result_light, "assertion_error_message", None),
            "task_id": _safe_attr(task_result_light, "task_id", None),
            "task_name": _safe_attr(task_result_light, "task_name", None),
        }

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

    steps = res.get("planner_steps", None)
    if steps is not None:
        shaped["planner_steps"] = steps

    planned_tools = res.get("planned_tools", None)
    if planned_tools is not None:
        shaped["planned_tools"] = planned_tools

    raw_logs = res.get("raw_logs", None)
    if raw_logs is not None and isinstance(raw_logs, dict):
        shaped["raw_logs"] = raw_logs
    else:
        shaped["raw_logs"] = {"tools": [], "llms": []}

    return shaped


# ──────────────────────────────────────────────────────────────────────────────
# Per-entry runner
# ──────────────────────────────────────────────────────────────────────────────
async def _run_entry_with_agent(
    agent: Any,
    entry: Dict[str, Any],
    variation_index: int,
    agent_tag: str,
    logger: logging.Logger,
) -> Dict[str, Any]:
    """Run one task entry through `agent.arun_task_entry(entry)` and return a
    JSON-serializable payload. On exception, returns a shaped error payload so
    summary/CSV stay consistent."""
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
        await asyncio.sleep(2)
    except Exception as e:
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
            "raw_logs": {"tools": [], "llms": []},
            **prov,
        }

    shaped = _result_to_json_friendly(res)
    prov = _provenance(agent)
    shaped["variation"] = variation_index
    shaped["agent_tag"] = agent_tag
    shaped["difficulty_level"] = entry.get("difficulty_level")
    return {**shaped, **prov}


# ──────────────────────────────────────────────────────────────────────────────
# Summary helpers
# ──────────────────────────────────────────────────────────────────────────────
def _summary_bump(
    summary: Dict[str, Dict[str, Dict[str, int]]],
    task_key: str,
    agent_tag: str,
    success: bool,
    light_success: Optional[bool] = None,
) -> None:
    if task_key not in summary:
        summary[task_key] = {}
    if agent_tag not in summary[task_key]:
        summary[task_key][agent_tag] = {"success": 0, "total": 0, "light_success": 0, "light_total": 0}
    summary[task_key][agent_tag]["total"] += 1
    if success:
        summary[task_key][agent_tag]["success"] += 1
    if light_success is not None:
        summary[task_key][agent_tag]["light_total"] += 1
        if light_success:
            summary[task_key][agent_tag]["light_success"] += 1


def _write_summary_csv(out_dir: Path, summary: Dict[str, Dict[str, Dict[str, int]]]) -> Path:
    """Compact CSV with full + light S/T per task × config."""
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
    empty = {"success": 0, "total": 0, "light_success": 0, "light_total": 0}
    for task_key, per_agent in sorted(summary.items()):
        b0 = per_agent.get("baseline_nomemory", empty)
        br = per_agent.get("baseline_with_references", empty)
        bm_no = per_agent.get("baseline_with_memory_no_spec", empty)
        bm_spec_trained = per_agent.get("baseline_mem_spec_trained", empty)
        bm_with = per_agent.get("baseline_with_memory_and_references", empty)
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
# Per-variation orchestrator core (shared by 5-tag and single-tag runners)
# ──────────────────────────────────────────────────────────────────────────────
async def _execute_variations(
    agents: Dict[str, Any],
    variations: List[Dict[str, Any]],
    out_dir: Path,
    logger: logging.Logger,
    tag_list: List[str],
    suffixes: Dict[str, str],
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, Dict[str, Dict[str, int]]]]:
    """Iterate every variation × every tag, write per-run JSONs, accumulate
    summary stats. Returns (overall, summary). Caller handles printing + CSV
    so different runners can present results differently."""
    variation_counter: Dict[Tuple[str, str], int] = {}
    overall: Dict[str, Dict[str, int]] = {t: {"success": 0, "total": 0} for t in tag_list}
    summary: Dict[str, Dict[str, Dict[str, int]]] = {}

    for i, entry in enumerate(variations, start=1):
        task_module: str = entry.get("module", "")
        task_class: str = entry.get("class", "")
        key = (task_module, task_class)
        next_idx = variation_counter.get(key, 0) + 1
        variation_counter[key] = next_idx

        logger.info(
            "[%d/%d] %s.%s (variation %d): running %d configs",
            i, len(variations), task_module, task_class, next_idx, len(tag_list),
        )

        per_config_results: Dict[str, Dict[str, Any]] = {}
        for tag in tag_list:
            res = await _run_entry_with_agent(
                agent=agents[tag],
                entry=entry,
                variation_index=next_idx,
                agent_tag=tag,
                logger=logger,
            )
            per_config_results[tag] = res

        safe_task = f"{task_module}".replace("/", "_")
        out_paths: List[Path] = []
        for tag in tag_list:
            suffix = suffixes.get(tag, tag)
            base_name = f"{safe_task}_v{next_idx}_{suffix}"
            out_paths.append(write_json(out_dir, base_name, per_config_results[tag]))
        logger.info("Wrote traces → %s", " | ".join(map(str, out_paths)))

        task_key = f"{task_module}.{task_class}"
        for tag in tag_list:
            success = _bool(_safe_attr(per_config_results[tag].get("task_result", {}), "task_success", False))
            light_result = per_config_results[tag].get("task_result_light", {})
            light_success = _safe_attr(light_result, "task_success", None)
            _summary_bump(summary, task_key, tag, success, light_success)
            overall[tag]["total"] += 1
            if success:
                overall[tag]["success"] += 1

    return overall, summary


def _fmt_full_light(d: Dict[str, int]) -> str:
    full = f"{d['success']}/{d['total']}"
    if d["light_total"] > 0:
        return f"{full} | {d['light_success']}/{d['light_total']}"
    return f"{full} | N/A"


# ──────────────────────────────────────────────────────────────────────────────
# 5-tag orchestrator (LangChain runner)
# ──────────────────────────────────────────────────────────────────────────────
async def run_variations(
    agents: Dict[str, Any],
    variations: List[Dict[str, Any]],
    out_dir: Path,
    logger: logging.Logger,
    tags: Optional[List[str]] = None,
    name_map_suffixes: Optional[Dict[str, str]] = None,
) -> None:
    """5-tag flow used by the LangChain baseline runner. Prints the per-task
    table with one F/L column per LangChain config and writes the canonical
    20-column CSV (downstream analysis scripts depend on this column order)."""
    tag_list = list(tags) if tags is not None else list(DEFAULT_TAGS)
    suffixes = dict(name_map_suffixes) if name_map_suffixes is not None else dict(DEFAULT_NAME_MAP_SUFFIXES)

    overall, summary = await _execute_variations(
        agents=agents, variations=variations, out_dir=out_dir, logger=logger,
        tag_list=tag_list, suffixes=suffixes,
    )

    # ---- Print summary
    logger.info("=== SUMMARY: Success by task and config (Full/Light) ===")
    header = (
        f"{'Task':50s}  {'NoMem F/L':14s}  {'WithRefs F/L':16s}  "
        f"{'Mem-NoSpec F/L':18s}  {'Mem-SpecTrain F/L':20s}  {'Mem+Refs F/L':16s}"
    )
    logger.info(header)
    logger.info("-" * len(header))
    empty = {"success": 0, "total": 0, "light_success": 0, "light_total": 0}
    for task_key, per_agent in sorted(summary.items()):
        b0 = per_agent.get("baseline_nomemory", empty)
        br = per_agent.get("baseline_with_references", empty)
        bm_no = per_agent.get("baseline_with_memory_no_spec", empty)
        bm_spec_trained = per_agent.get("baseline_mem_spec_trained", empty)
        bm_with = per_agent.get("baseline_with_memory_and_references", empty)
        row = (
            f"{task_key:50s}  {_fmt_full_light(b0):14s}  {_fmt_full_light(br):16s}  "
            f"{_fmt_full_light(bm_no):18s}  {_fmt_full_light(bm_spec_trained):20s}  "
            f"{_fmt_full_light(bm_with):16s}"
        )
        logger.info(row)

    logger.info("-" * len(header))
    logger.info(
        "OVERALL → NoMem: %d/%d | WithRefs: %d/%d | Mem-NoSpec: %d/%d | "
        "Mem-SpecTrained: %d/%d | Mem+Refs: %d/%d",
        overall["baseline_nomemory"]["success"], overall["baseline_nomemory"]["total"],
        overall["baseline_with_references"]["success"], overall["baseline_with_references"]["total"],
        overall["baseline_with_memory_no_spec"]["success"], overall["baseline_with_memory_no_spec"]["total"],
        overall["baseline_mem_spec_trained"]["success"], overall["baseline_mem_spec_trained"]["total"],
        overall["baseline_with_memory_and_references"]["success"], overall["baseline_with_memory_and_references"]["total"],
    )

    csv_path = _write_summary_csv(out_dir, summary)
    logger.info("Summary CSV written to: %s", csv_path)


# ──────────────────────────────────────────────────────────────────────────────
# Single-tag orchestrator (Claude Code runner; one config only)
# ──────────────────────────────────────────────────────────────────────────────
def _write_summary_csv_single(out_dir: Path, tag: str, summary: Dict[str, Dict[str, Dict[str, int]]]) -> Path:
    """4-column CSV for a single-tag run: Task, <Tag>_S, <Tag>_T, <Tag>_Light_S, <Tag>_Light_T."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"experiment_summary_{ts}.csv"
    headers = ["Task", f"{tag}_S", f"{tag}_T", f"{tag}_Light_S", f"{tag}_Light_T"]
    rows: List[List[str]] = []
    empty = {"success": 0, "total": 0, "light_success": 0, "light_total": 0}
    for task_key, per_agent in sorted(summary.items()):
        d = per_agent.get(tag, empty)
        rows.append([
            task_key,
            str(d["success"]), str(d["total"]),
            str(d["light_success"]), str(d["light_total"]),
        ])
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return out_path


async def run_variations_single(
    agent: Any,
    variations: List[Dict[str, Any]],
    out_dir: Path,
    logger: logging.Logger,
    tag: str = "claude_code",
    name_suffix: Optional[str] = None,
) -> None:
    """Single-tag flow used by the Claude Code runner. Writes one JSON per
    variation (named …_v{N}_{tag}.json) and a 4-column CSV summary."""
    suffix = name_suffix or tag
    overall, summary = await _execute_variations(
        agents={tag: agent}, variations=variations, out_dir=out_dir, logger=logger,
        tag_list=[tag], suffixes={tag: suffix},
    )

    logger.info("=== SUMMARY: Success by task (Full/Light) ===")
    header = f"{'Task':60s}  {tag + ' F/L':24s}"
    logger.info(header)
    logger.info("-" * len(header))
    empty = {"success": 0, "total": 0, "light_success": 0, "light_total": 0}
    for task_key, per_agent in sorted(summary.items()):
        d = per_agent.get(tag, empty)
        logger.info(f"{task_key:60s}  {_fmt_full_light(d):24s}")
    logger.info("-" * len(header))
    logger.info(
        "OVERALL → %s: %d/%d",
        tag, overall[tag]["success"], overall[tag]["total"],
    )

    csv_path = _write_summary_csv_single(out_dir, tag, summary)
    logger.info("Summary CSV written to: %s", csv_path)
