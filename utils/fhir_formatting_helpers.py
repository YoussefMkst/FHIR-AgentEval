"""
FHIR formatting helpers: convert trace callbacks into ExecutionResult-shaped
metadata expected by tasks/fhir_tasks_modular/task_interface_modular.py.

Exports:
- build_fhir_execution_metadata(...): aggregate ToolCallRecorder and
  LLMUsageRecorder into fields: response_msg, input_query, token_total,
  total_exec_ms, tool_order, tool_exec_ms, tool_calls, tool_call_counts.
"""

from __future__ import annotations

import ast
import json
import time
from typing import Any, Dict, List, Optional


def build_fhir_execution_metadata(
    prompt: str,
    final_text: str,
    started_at: float,
    tool_recorder: Any,
    llm_recorder: Any,
    name_aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Convert trace callbacks into ExecutionResult-shaped fields for FHIR tasks.

    Parameters
    - prompt:      task.get_prompt() used for this run
    - final_text:  model's final answer text
    - started_at:  wall-clock perf_counter() timestamp taken before inference
    - tool_recorder: ToolCallRecorder instance (with .records)
    - llm_recorder:  LLMUsageRecorder instance (with token totals)
    - name_aliases:  optional mapping to duplicate entries under alias keys
                     (e.g., {"getResourceById": "getResource"}) for
                     compatibility with evaluators

    Returns a dict compatible with ExecutionResult fields.
    """

    # 1) tool_order in chronological order
    ordered_records = sorted(getattr(tool_recorder, "records", []), key=lambda x: x.get("order", 0))
    tool_order: List[str] = [(r.get("name") or "tool") for r in ordered_records]

    # 2) aggregate per-tool timings and counts
    tool_exec_ms: Dict[str, float] = {}
    tool_call_counts: Dict[str, int] = {}
    for r in ordered_records:
        name = r.get("name") or "tool"
        tool_exec_ms[name] = tool_exec_ms.get(name, 0.0) + float(r.get("duration_ms") or 0.0)
        tool_call_counts[name] = tool_call_counts.get(name, 0) + 1

    # 3) group calls per tool with parsed inputs for downstream checks
    tool_calls: Dict[str, List[Dict[str, Any]]] = {}
    for r in ordered_records:
        name = r.get("name") or "tool"
        raw_in = r.get("input")
        parsed_in: Dict[str, Any] = {}
        try:
            if isinstance(raw_in, str):
                # Try JSON first, then Python literal eval
                try:
                    parsed_in = json.loads(raw_in)
                except json.JSONDecodeError:
                    parsed_in = ast.literal_eval(raw_in)
            elif isinstance(raw_in, dict):
                parsed_in = raw_in
        except Exception as e:
            # Keep the original string if parsing fails
            parsed_in = {"_raw_input": raw_in, "_parse_error": str(e)}
        call = {"input": parsed_in, "output": r.get("output")}
        tool_calls.setdefault(name, []).append(call)
        if name_aliases and name in name_aliases:
            tool_calls.setdefault(name_aliases[name], []).append(call)

    # 4) tokens and wall-clock
    token_total = int(getattr(llm_recorder, "total_tokens", 0) or 0)
    total_exec_ms = round((time.perf_counter() - started_at) * 1000.0, 3)

    return {
        "response_msg": final_text,
        "input_query": prompt,
        "token_total": token_total,
        "total_exec_ms": total_exec_ms,
        "tool_order": tool_order,
        "tool_exec_ms": tool_exec_ms,
        "tool_calls": tool_calls,
        "tool_call_counts": tool_call_counts,
    }


